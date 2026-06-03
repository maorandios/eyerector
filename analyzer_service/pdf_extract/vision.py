"""Render PDF plan sheets and extract steel geometry with OpenAI vision (multimodal)."""

from __future__ import annotations

import base64
import os
import time

import fitz

from analyzer_service.llm_extractor import LlmExtractionError, PURE_VECTOR_PROMPT, _openai_client
from analyzer_service.pdf_extract.vector_geometry import select_primary_plan_page_index
from analyzer_service.pdf_validate.sanitize import parse_pure_model_from_llm_json
from analyzer_service.pdf_validate.connectivity import analyze_model_connectivity
from analyzer_service.schemas import PureSteelElementSpec, PureSlabBoxSpec, PureStructuralModelSpec

VISION_USER_PREFIX = """You are reading ONE structural steel plan sheet (image).
Extract PureStructuralModelSpec JSON with all coordinates in millimetres in a SINGLE global system:

- Use the drawing grid: read axis labels, overall lengths, and grid spacing (e.g. 6000 mm bays).
- Place the building origin at the lower-left of the grid on this sheet (min X, min Y at ground).
- Map every visible column, beam, brace, purlin, and girder as a line segment (start → end).
- Columns: vertical segments (start_z ≠ end_z). Beams: mostly constant Z. Read level marks for Z.
- Use profile names shown (HEB, IPE, RHS, …) or sensible defaults.
- Slabs only in slabs[] as boxes. Do not invent a generic warehouse or portal frame — match THIS sheet only.
- NEVER output a placeholder demo (4 corner columns + perimeter beams only). If unreadable, return only members you clearly see.
- Do not copy members from other sheets. Coordinates must line up with printed dimensions.

Output ONLY valid JSON matching PureStructuralModelSpec."""


def _vision_model_candidates() -> list[str]:
    """Models to try in order (first match wins; skips models the API key cannot use)."""
    explicit = os.getenv("OPENAI_VISION_MODEL", "").strip()
    general = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    ordered = [
        explicit,
        "gpt-4o-2024-11-20",
        "gpt-4o",
        general,
        "gpt-4o-mini",
        "gpt-4.1-mini",
        "gpt-4.1",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for name in ordered:
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out or ["gpt-4o-mini"]


def _vision_model_name() -> str:
    return _vision_model_candidates()[0]


def _is_model_access_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "model_not_found" in text
        or "does not have access to model" in text
        or ("error code: 403" in text and "model" in text)
    )


def _vision_timeout_seconds() -> float:
    try:
        return float(os.getenv("PDF_VISION_TIMEOUT_SEC", "240"))
    except ValueError:
        return 240.0


def render_pdf_page_pngs(
    data: bytes,
    *,
    max_pages: int | None = None,
    dpi: int | None = None,
    only_page_index: int | None = None,
) -> list[tuple[int, bytes]]:
    limit = max_pages
    if limit is None:
        try:
            limit = int(os.getenv("PDF_VISION_MAX_PAGES", "12").strip())
        except ValueError:
            limit = 12
    if dpi is None:
        try:
            dpi = int(os.getenv("PDF_VISION_DPI", "300").strip())
        except ValueError:
            dpi = 300

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pages: list[tuple[int, bytes]] = []
        for index, page in enumerate(doc):
            if index >= limit:
                break
            page_num = index + 1
            if only_page_index is not None and index != only_page_index:
                continue
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            pages.append((page_num, pix.tobytes("png")))
        return pages
    finally:
        doc.close()


def _vision_max_tokens() -> int:
    try:
        return int(os.getenv("PDF_VISION_MAX_TOKENS", "16384"))
    except ValueError:
        return 16384


def _vision_use_strict_schema() -> bool:
    return os.getenv("PDF_VISION_STRICT_JSON", "0").strip().lower() in ("1", "true", "yes")


def _render_page_quadrant_pngs(
    data: bytes,
    page_index: int,
    *,
    dpi: int | None = None,
) -> list[tuple[str, bytes, fitz.Rect]]:
    """Four zoomed crops of one plan sheet so GPT-4o can read dense linework."""
    if dpi is None:
        try:
            dpi = int(os.getenv("PDF_VISION_QUADRANT_DPI", "400"))
        except ValueError:
            dpi = 400

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if page_index < 0 or page_index >= doc.page_count:
            return []
        page = doc[page_index]
        rect = page.rect
        mx = (rect.x0 + rect.x1) / 2.0
        my = (rect.y0 + rect.y1) / 2.0
        clips: list[tuple[str, fitz.Rect]] = [
            ("top-left", fitz.Rect(rect.x0, rect.y0, mx, my)),
            ("top-right", fitz.Rect(mx, rect.y0, rect.x1, my)),
            ("bottom-left", fitz.Rect(rect.x0, my, mx, rect.y1)),
            ("bottom-right", fitz.Rect(mx, my, rect.x1, rect.y1)),
        ]
        out: list[tuple[str, bytes, fitz.Rect]] = []
        for label, clip in clips:
            pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
            out.append((label, pix.tobytes("png"), clip))
        return out
    finally:
        doc.close()


def _estimate_mm_per_point(page: fitz.Page, model: PureStructuralModelSpec) -> float | None:
    """Calibrate PDF points → mm from the full-sheet vision bbox."""
    if not model.elements:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for el in model.elements:
        xs.extend((float(el.start_x), float(el.end_x)))
        ys.extend((float(el.start_y), float(el.end_y)))
    span_mm = max(max(xs) - min(xs), max(ys) - min(ys))
    if span_mm < 3000:
        return None
    page_pts = max(float(page.rect.width), float(page.rect.height))
    if page_pts <= 0:
        return None
    return span_mm / page_pts


def _crop_global_offset_mm(clip: fitz.Rect, page_height: float, mm_per_pt: float) -> tuple[float, float]:
    """Lower-left corner of a PDF crop rect in global mm (vision uses min X, min Y at ground)."""
    ox = float(clip.x0) * mm_per_pt
    oy = (float(page_height) - float(clip.y1)) * mm_per_pt
    return ox, oy


def _shift_model_to_crop_global(
    model: PureStructuralModelSpec,
    *,
    clip: fitz.Rect,
    page_height: float,
    mm_per_pt: float,
) -> PureStructuralModelSpec:
    ox, oy = _crop_global_offset_mm(clip, page_height, mm_per_pt)
    shifted: list[PureSteelElementSpec] = []
    for el in model.elements:
        shifted.append(
            el.model_copy(
                update={
                    "start_x": float(el.start_x) + ox,
                    "start_y": float(el.start_y) + oy,
                    "end_x": float(el.end_x) + ox,
                    "end_y": float(el.end_y) + oy,
                }
            )
        )
    return PureStructuralModelSpec(elements=shifted, slabs=model.slabs)


def _segment_dedup_key(el: PureSteelElementSpec, grid_mm: float) -> tuple:
    def q(v: float) -> int:
        return int(round(v / grid_mm))

    a = (q(el.start_x), q(el.start_y), q(el.start_z), q(el.end_x), q(el.end_y), q(el.end_z))
    b = (a[3], a[4], a[5], a[0], a[1], a[2])
    return a if a <= b else b


def _dedupe_elements(
    elements: list[PureSteelElementSpec],
    *,
    grid_mm: float = 250.0,
) -> tuple[list[PureSteelElementSpec], int]:
    best: dict[tuple, PureSteelElementSpec] = {}
    for el in elements:
        key = _segment_dedup_key(el, grid_mm)
        prev = best.get(key)
        if prev is None:
            best[key] = el
            continue
        dx = float(el.end_x) - float(el.start_x)
        dy = float(el.end_y) - float(el.start_y)
        dz = float(el.end_z) - float(el.start_z)
        new_len = dx * dx + dy * dy + dz * dz
        pdx = float(prev.end_x) - float(prev.start_x)
        pdy = float(prev.end_y) - float(prev.start_y)
        pdz = float(prev.end_z) - float(prev.start_z)
        if new_len > pdx * pdx + pdy * pdy + pdz * pdz:
            best[key] = el
    dropped = len(elements) - len(best)
    return list(best.values()), dropped


def _merge_vision_submodels(
    labeled: list[tuple[str, PureStructuralModelSpec]],
    *,
    page: fitz.Page,
    mm_per_pt: float | None,
    clips: dict[str, fitz.Rect],
) -> tuple[PureStructuralModelSpec, list[str]]:
    warnings: list[str] = []
    if not labeled:
        raise LlmExtractionError("No vision submodels to merge")

    page_h = float(page.rect.height)
    combined: list[PureSteelElementSpec] = []
    for label, model in labeled:
        if label != "full" and mm_per_pt and label in clips:
            model = _shift_model_to_crop_global(
                model,
                clip=clips[label],
                page_height=page_h,
                mm_per_pt=mm_per_pt,
            )
            warnings.append(
                f"Aligned quadrant '{label}' to global mm using crop offset "
                f"({mm_per_pt:.4g} mm/pt from full sheet)."
            )
        combined.extend(model.elements)

    try:
        grid_mm = float(os.getenv("PDF_VISION_DEDUP_GRID_MM", "250"))
    except ValueError:
        grid_mm = 250.0
    deduped, dropped = _dedupe_elements(combined, grid_mm=grid_mm)
    if dropped:
        warnings.append(f"Deduplicated {dropped} duplicate/near-duplicate segments after merge.")

    if not deduped:
        raise LlmExtractionError("Vision merge produced no steel elements")

    merged = PureStructuralModelSpec(elements=deduped, slabs=None)
    conn = analyze_model_connectivity(merged)
    warnings.append(f"Connectivity: {conn.summary()}")
    if conn.is_fragmented:
        warnings.append(
            "Model looks fragmented (disconnected clusters / floating members). "
            "Vision likely invented partial frames instead of reading the full plan — "
            "use AI Designer for a complete building or CAD vector import."
        )
    return merged, warnings


def _merge_models(models: list[PureStructuralModelSpec]) -> PureStructuralModelSpec:
    if not models:
        raise LlmExtractionError("No models to merge")
    if len(models) == 1:
        return models[0]
    pairs = [(index + 1, model) for index, model in enumerate(models)]
    return _merge_page_models(pairs)


def _call_vision_llm(
    user_parts: list[dict],
    *,
    model_name: str | None = None,
) -> tuple[PureStructuralModelSpec, list[str], str]:
    client = _openai_client()
    candidates = [model_name] if model_name else _vision_model_candidates()
    last_error: Exception | None = None

    for model in candidates:
        if not model:
            continue
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": PURE_VECTOR_PROMPT},
                    {"role": "user", "content": user_parts},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "pure_structural_model",
                        "strict": _vision_use_strict_schema(),
                        "schema": PureStructuralModelSpec.openai_strict_json_schema(),
                    },
                },
                max_tokens=_vision_max_tokens(),
                timeout=_vision_timeout_seconds(),
            )
            raw = completion.choices[0].message.content
            if not raw:
                raise LlmExtractionError("Vision model returned empty PureStructuralModelSpec content")
            parsed, sanitize_warnings = parse_pure_model_from_llm_json(raw)
            return parsed, sanitize_warnings, model
        except Exception as exc:
            if _is_model_access_error(exc):
                last_error = exc
                continue
            raise

    raise LlmExtractionError(
        "No OpenAI vision model available for this API key. "
        f"Tried: {', '.join(candidates)}. "
        f"Set OPENAI_VISION_MODEL to a model your project supports (e.g. gpt-4o-mini). "
        f"Last error: {last_error}"
    )


def _merge_page_models(page_models: list[tuple[int, PureStructuralModelSpec]]) -> PureStructuralModelSpec:
    elements: list[PureSteelElementSpec] = []
    slabs: list[PureSlabBoxSpec] = []
    seen_ids: set[str] = set()

    for page_num, model in page_models:
        for el in model.elements:
            base_id = el.id
            new_id = f"p{page_num}_{base_id}"
            suffix = 1
            while new_id in seen_ids:
                suffix += 1
                new_id = f"p{page_num}_{base_id}_{suffix}"
            seen_ids.add(new_id)
            elements.append(el.model_copy(update={"id": new_id}))
        for slab in model.slabs or []:
            base_id = slab.id
            new_id = f"p{page_num}_{base_id}"
            suffix = 1
            while new_id in seen_ids:
                suffix += 1
                new_id = f"p{page_num}_{base_id}_{suffix}"
            seen_ids.add(new_id)
            slabs.append(slab.model_copy(update={"id": new_id}))

    if not elements:
        raise LlmExtractionError("Vision extraction produced no steel elements across all pages")
    return PureStructuralModelSpec(elements=elements, slabs=slabs or None)


def _vision_extract_crop(
    page_num: int,
    png: bytes,
    *,
    crop_label: str,
    text_context: str,
    scale_note: str | None,
    extra_hints: str | None,
    crop_bounds_mm: str | None = None,
) -> tuple[PureStructuralModelSpec, list[str], str]:
    region_note = (
        f"You are viewing sheet {page_num}, region: {crop_label}. "
        "Extract EVERY steel member visible in this image."
    )
    if crop_bounds_mm:
        region_note += (
            f"\nThis crop covers the following global mm bounds on the full plan: {crop_bounds_mm}. "
            "Return coordinates in that SAME global system (do not use a local 0,0 for this crop only)."
        )
    else:
        region_note += " Use the same global mm grid as the full structural sheet."

    user_parts: list[dict] = [
        {
            "type": "text",
            "text": f"{VISION_USER_PREFIX}\n\n{region_note}",
        },
    ]
    if scale_note:
        user_parts.append({"type": "text", "text": f"Scale / units hint: {scale_note}"})
    if extra_hints:
        user_parts.append({"type": "text", "text": f"Additional hints: {extra_hints}"})
    if text_context.strip():
        user_parts.append(
            {
                "type": "text",
                "text": f"PDF text labels (same document):\n{text_context[:6000]}",
            }
        )
    encoded = base64.standard_b64encode(png).decode("ascii")
    user_parts.append(
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "high"},
        }
    )
    return _call_vision_llm(user_parts)


def _vision_extract_single_page(
    page_num: int,
    png: bytes,
    *,
    text_context: str,
    scale_note: str | None,
    extra_hints: str | None,
) -> tuple[PureStructuralModelSpec, list[str], str]:
    return _vision_extract_crop(
        page_num,
        png,
        crop_label="full sheet",
        text_context=text_context,
        scale_note=scale_note,
        extra_hints=extra_hints,
    )


def _format_crop_bounds_mm(
    clip: fitz.Rect,
    page_height: float,
    mm_per_pt: float,
) -> str:
    x0, y0 = _crop_global_offset_mm(clip, page_height, mm_per_pt)
    x1 = float(clip.x1) * mm_per_pt
    y1 = (float(page_height) - float(clip.y0)) * mm_per_pt
    return f"X {x0:.0f}–{x1:.0f} mm, Y {y0:.0f}–{y1:.0f} mm"


def _vision_extract_page_with_quadrants(
    data: bytes,
    page_index: int,
    page_num: int,
    full_png: bytes,
    *,
    text_context: str,
    scale_note: str | None,
    extra_hints: str | None,
) -> tuple[PureStructuralModelSpec, list[str], str]:
    """Full sheet + 4 zoomed quadrants when the plan is too dense for one pass."""
    warnings: list[str] = []
    labeled: list[tuple[str, PureStructuralModelSpec]] = []
    model_used = _vision_model_name()

    full_model, full_warn, model_used = _vision_extract_single_page(
        page_num,
        full_png,
        text_context=text_context,
        scale_note=scale_note,
        extra_hints=extra_hints,
    )
    warnings.extend(full_warn)
    labeled.append(("full", full_model))
    warnings.append(f"Sheet {page_num} full: {len(full_model.elements)} members")

    min_for_quadrants = int(os.getenv("PDF_VISION_QUADRANT_THRESHOLD", "25"))
    use_quadrants = os.getenv("PDF_VISION_USE_QUADRANTS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if len(full_model.elements) >= min_for_quadrants or not use_quadrants:
        conn = analyze_model_connectivity(full_model)
        warnings.append(f"Connectivity: {conn.summary()}")
        return full_model, warnings, model_used

    warnings.append(
        f"Sheet {page_num}: only {len(full_model.elements)} members on full view — "
        "running 4 quadrant zoom passes for dense CAD linework."
    )

    quadrants = _render_page_quadrant_pngs(data, page_index)
    clips = {label: clip for label, _png, clip in quadrants}
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        page = doc[page_index]
        page_h = float(page.rect.height)
        mm_per_pt = _estimate_mm_per_point(page, full_model)
        if mm_per_pt is None:
            warnings.append(
                "Could not calibrate crop offsets from full sheet — quadrant coords may be wrong; "
                "set PDF_VISION_USE_QUADRANTS=0 to use full sheet only."
            )
        for label, qpng, clip in quadrants:
            bounds_hint = None
            if mm_per_pt:
                bounds_hint = _format_crop_bounds_mm(clip, page_h, mm_per_pt)
            try:
                qmodel, qwarn, qmodel_name = _vision_extract_crop(
                    page_num,
                    qpng,
                    crop_label=label,
                    text_context=text_context,
                    scale_note=scale_note,
                    extra_hints=extra_hints,
                    crop_bounds_mm=bounds_hint,
                )
                model_used = qmodel_name
                warnings.extend(qwarn)
                labeled.append((label, qmodel))
                warnings.append(f"Sheet {page_num} {label}: {len(qmodel.elements)} members")
            except Exception as exc:
                warnings.append(f"Sheet {page_num} {label} failed: {exc}")

        merged, merge_warn = _merge_vision_submodels(
            labeled,
            page=page,
            mm_per_pt=mm_per_pt,
            clips=clips,
        )
        warnings.extend(merge_warn)
    finally:
        doc.close()

    warnings.append(f"Sheet {page_num} merged total: {len(merged.elements)} members")
    return merged, warnings, model_used


ENRICHED_RETRY_SUFFIX = """
SECOND PASS — be exhaustive:
- List every beam, column, brace, purlin, girder, truss member as its own element.
- Do not return a single box, outline, or fewer than 20 members for a full structural sheet.
- Use mm coordinates from dimensions on the drawing.
- Never use identical start and end coordinates.
"""


def extract_pure_model_from_pdf_vision(
    data: bytes,
    *,
    text_context: str = "",
    scale_note: str | None = None,
    extra_hints: str | None = None,
    retry_enriched: bool = False,
    only_page_index: int | None = None,
) -> tuple[PureStructuralModelSpec, str, list[str]]:
    """
    AI vision extraction: PDF pages → images → OpenAI → PureStructuralModelSpec.
    Returns (model, model_name_used, warnings).
    """
    all_warnings: list[str] = []

    if only_page_index is None and os.getenv("PDF_VISION_ALL_PAGES", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        only_page_index = select_primary_plan_page_index(data)
        all_warnings.append(
            f"Auto-selected sheet {only_page_index + 1} as the main plan "
            "(one sheet only — multi-page merge causes wrong 3D). "
            "Set Hints: page N or PDF_VISION_ALL_PAGES=1 for all sheets."
        )

    pages = render_pdf_page_pngs(data, only_page_index=only_page_index)
    if not pages:
        hint = (
            f"page {only_page_index + 1} not found in PDF"
            if only_page_index is not None
            else "PDF has no pages"
        )
        raise LlmExtractionError(f"Cannot render plan sheets for vision: {hint}")

    hints = (extra_hints or "") + (ENRICHED_RETRY_SUFFIX if retry_enriched else "")
    page_models: list[tuple[int, PureStructuralModelSpec]] = []
    page_errors: list[str] = []
    model_used = _vision_model_name()

    pause_sec = float(os.getenv("PDF_VISION_PAGE_PAUSE_SEC", "1.5"))

    sheet_index = (only_page_index if only_page_index is not None else pages[0][0] - 1)

    for page_num, png in pages:
        try:
            page_model, page_warnings, page_model_name = _vision_extract_page_with_quadrants(
                data,
                sheet_index,
                page_num,
                png,
                text_context=text_context,
                scale_note=scale_note,
                extra_hints=hints,
            )
            model_used = page_model_name
            all_warnings.extend(page_warnings)
            page_models.append((page_num, page_model))
            all_warnings.append(
                f"Sheet {page_num}: vision OK ({len(page_model.elements)} members, model {page_model_name})"
            )
        except Exception as exc:
            page_errors.append(f"sheet {page_num}: {exc}")
            all_warnings.append(f"Sheet {page_num}: vision failed — {exc}")
        if pause_sec > 0 and len(pages) > 1:
            time.sleep(pause_sec)

    if not page_models:
        raise LlmExtractionError(
            "OpenAI vision failed on every sheet: " + "; ".join(page_errors[:6])
        )

    if page_errors:
        all_warnings.append(
            f"Vision partial success: {len(page_models)}/{len(pages)} sheet(s); "
            + "; ".join(page_errors[:4])
        )

    merged = _merge_page_models(page_models) if len(page_models) > 1 else page_models[0][1]

    if (
        not retry_enriched
        and len(merged.elements) < 20
        and only_page_index is None
        and len(pages) > 1
    ):
        return extract_pure_model_from_pdf_vision(
            data,
            text_context=text_context,
            scale_note=scale_note,
            extra_hints=extra_hints,
            retry_enriched=True,
            only_page_index=only_page_index,
        )

    if not retry_enriched and len(merged.elements) < 15:
        return extract_pure_model_from_pdf_vision(
            data,
            text_context=text_context,
            scale_note=scale_note,
            extra_hints=extra_hints,
            retry_enriched=True,
            only_page_index=only_page_index,
        )

    return merged, model_used, all_warnings

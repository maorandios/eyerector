"""PDF → PureStructuralModelSpec via AI (vision/text), then Python IFC compiler."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Literal

from analyzer_service.llm_extractor import (
    LlmExtractionError,
    PURE_VECTOR_PROMPT,
    _openai_client,
)
from analyzer_service.pdf_extract.vector_geometry import extract_pure_model_from_pdf_vectors
from analyzer_service.pdf_extract.vision import extract_pure_model_from_pdf_vision
from analyzer_service.pdf_ingest.ingest import PdfIngestReport, ingest_pdf_bytes
from analyzer_service.pdf_validate.align import align_pure_model_for_display
from analyzer_service.pdf_validate.completeness import check_extraction_completeness
from analyzer_service.pdf_validate.connectivity import analyze_model_connectivity
from analyzer_service.pdf_validate.schematic import detect_schematic_placeholder
from analyzer_service.pdf_validate.sanitize import parse_pure_model_from_llm_json
from analyzer_service.pdf_validate.validate import ValidationReport, validate_pure_model
from analyzer_service.schemas import PureStructuralModelSpec

PdfExtractionStatus = Literal["ok", "needs_review", "failed"]
ExtractionMethod = Literal["vision_llm", "text_llm", "vector_pdf"]


@dataclass
class PdfExtractionResult:
    status: PdfExtractionStatus
    ingest: PdfIngestReport
    validation: ValidationReport | None = None
    model: PureStructuralModelSpec | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    extraction_method: str = "vision_llm"
    ai_model: str | None = None


def _parse_page_index_from_hints(extra_hints: str | None) -> int | None:
    if not extra_hints:
        return None
    match = re.search(r"(?:sheet|page)\s*#?\s*(\d+)", extra_hints, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)) - 1


def _cad_lines_enabled() -> bool:
    """Legacy flag: force CAD vector line extraction."""
    return os.getenv("PDF_USE_CAD_LINES", "").strip().lower() in ("1", "true", "yes")


def _pdf_extract_mode() -> str:
    """auto | cad | vision — auto uses CAD vectors for dense structural PDFs."""
    return os.getenv("PDF_EXTRACT_MODE", "auto").strip().lower()


def _primary_extraction_method(ingest: PdfIngestReport) -> ExtractionMethod:
    """Dense CAD plans: read real PDF vector lines first; vision is fallback only."""
    mode = _pdf_extract_mode()
    if mode in ("vision", "ai"):
        return "vision_llm"
    if mode in ("cad", "vector", "lines") or _cad_lines_enabled():
        return "vector_pdf"
    if os.getenv("PDF_FORCE_TEXT_ONLY", "").strip().lower() in ("1", "true", "yes"):
        return "text_llm" if ingest.text_char_count >= 200 else "vision_llm"
    if ingest.text_char_count >= 12_000 and ingest.drawing_op_count < 300:
        return "text_llm"
    if ingest.drawing_op_count > 300 and ingest.likely_vector:
        return "vector_pdf"
    return "vision_llm"


def _is_drawing_heavy_pdf(ingest: PdfIngestReport) -> bool:
    return ingest.drawing_op_count > 200 or (
        ingest.likely_vector and ingest.drawing_op_count > 80
    )


def _fallback_methods(
    ingest: PdfIngestReport, primary: ExtractionMethod
) -> list[ExtractionMethod]:
    """Dense CAD: CAD lines first, then vision. Light PDFs: vision then text."""
    if _is_drawing_heavy_pdf(ingest):
        order: list[ExtractionMethod] = ["vector_pdf", "vision_llm"]
        chain = [primary] + [m for m in order if m != primary]
        return chain
    order = ["vision_llm", "text_llm"]
    chain = [primary] + [m for m in order if m != primary]
    if ingest.text_char_count < 80:
        chain = [m for m in chain if m != "text_llm"]
    return chain


def _extract_model_from_drawing_text(
    text: str,
    *,
    scale_note: str | None = None,
    extra_hints: str | None = None,
) -> tuple[PureStructuralModelSpec, str]:
    client = _openai_client()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    user_parts = [
        "Structural data extracted from a 2D steel plan PDF (text layer).",
        "Infer absolute 3D coordinates in millimetres from dimensions, grids, levels, and schedules.",
        "If scale is ambiguous, state assumptions in coordinates only — do not add commentary outside JSON.",
    ]
    if scale_note:
        user_parts.append(f"Scale / units hint: {scale_note}")
    if extra_hints:
        user_parts.append(f"Additional hints: {extra_hints}")
    user_parts.append("\n--- PDF TEXT ---\n")
    user_parts.append(text)

    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": PURE_VECTOR_PROMPT},
            {"role": "user", "content": "\n".join(user_parts)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "pure_structural_model",
                "strict": True,
                "schema": PureStructuralModelSpec.openai_strict_json_schema(),
            },
        },
    )
    raw = completion.choices[0].message.content
    if not raw:
        raise LlmExtractionError("OpenAI returned empty PureStructuralModelSpec content")
    model, _ = parse_pure_model_from_llm_json(raw)
    return model, model_name


def _run_extraction(
    method: ExtractionMethod,
    data: bytes,
    ingest: PdfIngestReport,
    *,
    scale_note: str | None,
    extra_hints: str | None,
) -> tuple[PureStructuralModelSpec, str | None, list[str]]:
    extra_warnings: list[str] = []
    if method == "vision_llm":
        model, ai_model, vision_warnings = extract_pure_model_from_pdf_vision(
            data,
            text_context=ingest.text_excerpt,
            scale_note=scale_note,
            extra_hints=extra_hints,
            only_page_index=_parse_page_index_from_hints(extra_hints),
        )
        extra_warnings.extend(vision_warnings)
        return model, ai_model, extra_warnings

    if method == "text_llm":
        if not ingest.text_excerpt.strip():
            raise LlmExtractionError("PDF has no text layer for text LLM extraction")
        model, ai_model = _extract_model_from_drawing_text(
            ingest.text_excerpt,
            scale_note=scale_note,
            extra_hints=extra_hints,
        )
        return model, ai_model, extra_warnings

    model, extra_warnings = extract_pure_model_from_pdf_vectors(
        data,
        scale_note=scale_note,
        page_index=_parse_page_index_from_hints(extra_hints),
    )
    return model, None, extra_warnings


def extract_structural_model_from_pdf(
    data: bytes,
    *,
    scale_note: str | None = None,
    extra_hints: str | None = None,
    skip_llm: bool = False,
) -> PdfExtractionResult:
    """PDF → AI JSON (PureStructuralModelSpec) → validation → ready for IFC compiler."""
    ingest = ingest_pdf_bytes(data)
    warnings = list(ingest.warnings)

    if skip_llm or os.getenv("PDF_EXTRACT_SKIP_LLM", "").strip().lower() in ("1", "true", "yes"):
        return PdfExtractionResult(
            status="needs_review",
            ingest=ingest,
            message="LLM extraction skipped (PDF_EXTRACT_SKIP_LLM). Review ingest text and provide JSON manually.",
            warnings=warnings,
        )

    primary = _primary_extraction_method(ingest)
    chain = _fallback_methods(ingest, primary)

    model: PureStructuralModelSpec | None = None
    extraction_method: ExtractionMethod = primary
    ai_model: str | None = None
    last_error: Exception | None = None

    for method in chain:
        try:
            model, ai_model, method_warnings = _run_extraction(
                method,
                data,
                ingest,
                scale_note=scale_note,
                extra_hints=extra_hints,
            )
            extraction_method = method
            warnings.extend(method_warnings)
            if method != primary:
                warnings.append(f"Primary method '{primary}' failed; succeeded with '{method}'.")
            break
        except Exception as exc:
            last_error = exc
            warnings.append(f"{method} failed: {exc}")
            continue

    if model is None:
        detail = str(last_error) if last_error else "unknown error"
        tried = ", ".join(chain)
        vision_errors = [w for w in warnings if w.startswith("vision_llm failed:")]
        if vision_errors:
            detail = vision_errors[-1].replace("vision_llm failed: ", "", 1)
        hint = (
            " OpenAI vision (gpt-4o) reads plan sheet images — not PDF text. "
            "Check OPENAI_API_KEY, OPENAI_VISION_MODEL (e.g. gpt-4o-mini), and Hints: page 1 for the main plan."
        )
        return PdfExtractionResult(
            status="failed",
            ingest=ingest,
            extraction_method=primary,
            message=f"AI PDF extraction failed (tried {tried}): {detail}.{hint}",
            warnings=warnings,
        )

    if extraction_method == "vision_llm" and os.getenv("PDF_ALIGN_GRID", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        model, align_warnings = align_pure_model_for_display(model)
        warnings.extend(align_warnings)

    completeness = check_extraction_completeness(model, ingest, extraction_method=extraction_method)

    vision_fragmented = False
    vision_placeholder = False
    if model is not None and extraction_method == "vision_llm":
        conn = analyze_model_connectivity(model)
        warnings.append(f"Pipeline connectivity: {conn.summary()}")
        if conn.is_fragmented:
            vision_fragmented = True
            warnings.append(
                "FAILURE STAGE: OpenAI vision — model is fragmented (disconnected members). "
                "IFC will not match the plan. Retry with Scale: units mm and Hints: page 1, "
                "or set PDF_EXTRACT_MODE=cad to force CAD line extraction."
            )
        schematic = detect_schematic_placeholder(
            model,
            dense_cad=_is_drawing_heavy_pdf(ingest),
        )
        if schematic.is_placeholder:
            vision_placeholder = True
            warnings.append(f"FAILURE STAGE: OpenAI vision — {schematic.reason}")

    if vision_placeholder:
        return PdfExtractionResult(
            status="failed",
            ingest=ingest,
            extraction_method=extraction_method,
            model=model,
            ai_model=ai_model,
            message=(
                f"[OpenAI vision ({ai_model or 'gpt-4o'})] {schematic.reason} "
                "Vision invented a demo frame instead of reading the plan. "
                "Restart the API and upload again — dense CAD PDFs now default to CAD vector extraction."
            ),
            warnings=warnings,
        )

    if not completeness.ok and extraction_method == "vision_llm":
        warnings.append(completeness.message)
        try:
            warnings.append("Retrying OpenAI vision with a second pass (enriched prompt).")
            model, ai_model, retry_warnings = extract_pure_model_from_pdf_vision(
                data,
                text_context=ingest.text_excerpt,
                scale_note=scale_note,
                extra_hints=(extra_hints or "") + "\nExtract every visible steel member; do not summarize.",
                retry_enriched=True,
                only_page_index=_parse_page_index_from_hints(extra_hints),
            )
            warnings.extend(retry_warnings)
            completeness = check_extraction_completeness(
                model, ingest, extraction_method="vision_llm"
            )
        except Exception as exc:
            warnings.append(f"Vision retry failed: {exc}")

    if not completeness.ok:
        prefix = ""
        if extraction_method == "vision_llm":
            prefix = f"[OpenAI vision ({ai_model or 'gpt-4o'})] "
        elif extraction_method == "text_llm":
            prefix = f"[OpenAI text ({ai_model or 'gpt-4o-mini'})] "
            if _is_drawing_heavy_pdf(ingest):
                prefix = "[Vision failed; text fallback is unreliable on CAD plans] "
        return PdfExtractionResult(
            status="failed",
            ingest=ingest,
            extraction_method=extraction_method,
            model=model,
            ai_model=ai_model,
            message=prefix + completeness.message,
            warnings=warnings,
        )

    if (
        extraction_method == "vision_llm"
        and len(model.elements) < 12
        and _is_drawing_heavy_pdf(ingest)
    ):
        warnings.append(
            f"Vision found {len(model.elements)} members — dense CAD PDFs may need the text AI Designer for a full model."
        )

    status: PdfExtractionStatus = "ok" if not warnings else "needs_review"
    if (
        extraction_method == "vision_llm"
        and _is_drawing_heavy_pdf(ingest)
        and len(model.elements) < 12
    ):
        warnings.append(
            f"Vision extracted {len(model.elements)} members — fewer than expected; review JSON before IFC export."
        )
        status = "needs_review"
    if vision_fragmented:
        status = "needs_review"

    validation = validate_pure_model(model)
    warnings.extend(validation.warnings)
    if not validation.ok:
        return PdfExtractionResult(
            status="failed",
            ingest=ingest,
            extraction_method=extraction_method,
            ai_model=ai_model,
            validation=validation,
            model=model,
            message="Extracted JSON failed validation: " + "; ".join(validation.errors),
            warnings=warnings,
        )

    if extraction_method == "vector_pdf":
        status = "needs_review"

    if extraction_method == "vision_llm":
        method_label = f"OpenAI vision ({ai_model or 'gpt-4o'})"
    elif extraction_method == "text_llm":
        method_label = f"OpenAI text ({ai_model or 'gpt-4o-mini'})"
    else:
        method_label = "CAD vector lines (no AI)"

    return PdfExtractionResult(
        status=status,
        ingest=ingest,
        validation=validation,
        model=model,
        extraction_method=extraction_method,
        ai_model=ai_model,
        message=(
            f"AI/JSON extraction complete via {method_label} "
            f"({len(model.elements)} members, {len(model.slabs or [])} slabs)."
        ),
        warnings=warnings,
    )

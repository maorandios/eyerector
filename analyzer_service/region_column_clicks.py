"""
Build structural grid from user-clicked column positions on the crop image.

Clicks choose which columns exist; PDF dimension chains supply bay spacing (mm).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

from analyzer_service.region_analysis_schemas import (
    ColumnPlacement,
    CropRectNorm,
    DetectedParameterEntry,
    RegionStructuralAnalysis,
)
from analyzer_service.region_grid_geometry import _crop_pixel_size
from analyzer_service.region_layout_compiler import _normalize_axis_positions
from analyzer_service.region_pdf_grid import (
    _clip_rect,
    _fitz_page_index,
    _text_spans_in_clip,
    extract_region_grid_from_pdf,
)
from analyzer_service.pdf_project_storage import project_dir

_CLUSTER_TOL_FRAC = 0.022
_MIN_CLICKS = 1
_PROFILE_RE = re.compile(
    r"\b(RHS\s*\d+\s*[xX×/]\s*\d+\s*[xX×/]\s*\d+(?:\.\d+)?|"
    r"SHS\s*\d+\s*[xX×/]\s*\d+(?:\.\d+)?|"
    r"HEB\s*\d+|HEA\s*\d+|IPE\s*\d+)\b",
    re.IGNORECASE,
)


@dataclass
class ColumnClick:
    x_px: float
    y_px: float
    x_norm: float | None = None
    y_norm: float | None = None
    x_pt: float | None = None
    y_pt: float | None = None
    mark: str | None = None
    id: str | None = None


def _cluster_axis_px(values: list[float], crop_span_px: int) -> list[float]:
    if not values:
        return []
    tol = max(14.0, crop_span_px * _CLUSTER_TOL_FRAC)
    sorted_vals = sorted(values)
    clusters: list[list[float]] = []
    for v in sorted_vals:
        if not clusters or v - clusters[-1][-1] > tol:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return [sum(c) / len(c) for c in clusters]


def _nearest_index(value: float, stations: list[float]) -> int:
    return min(range(len(stations)), key=lambda i: abs(stations[i] - value))


def _px_to_mm(value_px: float, origin_px: float, mm_per_px: float) -> float:
    return round((value_px - origin_px) * mm_per_px, 1)


def _valid_pdf_stations(stations: list[float]) -> bool:
    return len(stations) >= 2 and stations[-1] > stations[0]


def _detect_column_profile_from_page(page: fitz.Page, clip: fitz.Rect) -> str | None:
    """Pick the most common structural profile string in the crop (e.g. RHS100X100X5)."""
    counts: dict[str, int] = {}
    try:
        text = page.get_text("text", clip=clip) or ""
    except Exception:
        text = ""
    for span_text in (t[4] for t in _text_spans_in_clip(page, clip)):
        text = f"{text}\n{span_text}"
    for m in _PROFILE_RE.finditer(text):
        raw = re.sub(r"\s+", "", m.group(1).upper().replace("×", "X"))
        counts[raw] = counts.get(raw, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _load_pdf_grid(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
    *,
    scale_note: str | None = None,
):
    return extract_region_grid_from_pdf(
        project_id, page_index, crop, scale_note=scale_note
    )


def _build_aligned_grid_px(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
    crop_w: int,
    crop_h: int,
    xs_mm: list[float],
    ys_mm: list[float],
    *,
    scale_note: str | None = None,
    click_x_px: list[float] | None = None,
    click_y_px: list[float] | None = None,
) -> tuple[list[float], list[float], list[float], list[float], float | None, float | None, list[str]]:
    """Axis labels + long PDF vectors → aligned px grid (no dimension pseudo-px merge)."""
    from analyzer_service.region_grid_lines import build_crop_grid
    from analyzer_service.region_pdf_grid import _clip_rect, _fitz_page_index

    pdf_path = project_dir(project_id) / "source.pdf"
    if not pdf_path.is_file():
        return [], [], xs_mm, ys_mm, None, None, []

    pdf_grid = _load_pdf_grid(project_id, page_index, crop, scale_note=scale_note)
    doc = fitz.open(pdf_path)
    try:
        page = doc[_fitz_page_index(page_index)]
        clip = _clip_rect(page, crop)
        x_lines, y_lines, xs_out, ys_out, mm_x, mm_y, grid_notes = build_crop_grid(
            page,
            clip,
            crop_w,
            crop_h,
            pdf_grid,
            scale_note=scale_note,
            click_x_px=click_x_px,
            click_y_px=click_y_px,
        )
        return x_lines, y_lines, xs_out, ys_out, mm_x, mm_y, grid_notes
    finally:
        doc.close()


def _calibrate_mm_per_px(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
    crop_w: int,
    crop_h: int,
    *,
    scale_note: str | None = None,
) -> tuple[float | None, float | None, float | None, list[float], list[float], str | None, list[str]]:
    notes: list[str] = []
    pdf_grid = _load_pdf_grid(project_id, page_index, crop, scale_note=scale_note)
    suggested = None

    pdf_path = project_dir(project_id) / "source.pdf"
    if pdf_path.is_file():
        doc = fitz.open(pdf_path)
        try:
            page = doc[_fitz_page_index(page_index)]
            clip = _clip_rect(page, crop)
            suggested = _detect_column_profile_from_page(page, clip)
            if suggested:
                notes.append(f"Detected profile on sheet: {suggested}")
        finally:
            doc.close()

    if not pdf_grid or pdf_grid.confidence < 0.3:
        notes.append("PDF dimensions not found — bay spacing from click spacing only.")
        return None, None, None, [], [], suggested, notes

    xs = _normalize_axis_positions(list(pdf_grid.x_stations_mm))
    ys = _normalize_axis_positions(list(pdf_grid.y_stations_mm))
    span_w = xs[-1] if xs else None
    span_h = ys[-1] if ys else None

    mm_per_px = None
    mm_per_px_x = None
    mm_per_px_y = None
    if span_w and crop_w > 0:
        mm_per_px_x = span_w / crop_w
        mm_per_px = mm_per_px_x
    if span_h and crop_h > 0:
        mm_per_px_y = span_h / crop_h
    if mm_per_px_y is None:
        mm_per_px_y = mm_per_px_x
    if pdf_path.is_file() and mm_per_px_x is None:
        doc = fitz.open(pdf_path)
        try:
            page = doc[_fitz_page_index(page_index)]
            clip = _clip_rect(page, crop)
            from analyzer_service.pdf_extract.vector_geometry import (
                _infer_mm_per_unit,
                _segments_from_path,
            )

            segments: list = []
            for path in page.get_drawings():
                segments.extend(_segments_from_path(path, 0))
            mm_per_pt = _infer_mm_per_unit(
                [clip.x0, clip.x1, clip.y0, clip.y1], segments, scale_note
            )
            if crop_w > 0:
                mm_per_px_x = (clip.width * mm_per_pt) / crop_w
                mm_per_px = mm_per_px_x
            if crop_h > 0:
                mm_per_px_y = (clip.height * mm_per_pt) / crop_h
        finally:
            doc.close()

    if mm_per_px_x:
        notes.append(
            f"Bay spacing from PDF (conf={pdf_grid.confidence:.2f}): "
            f"X={len(xs)} Y={len(ys)} · "
            f"~{mm_per_px_x:.2f} mm/px (X) · ~{(mm_per_px_y or mm_per_px_x):.2f} mm/px (Y)"
        )
    return mm_per_px, span_w, span_h, xs, ys, suggested, notes


def crop_calibration(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
    *,
    scale_note: str | None = None,
) -> dict:
    crop_w, crop_h = _crop_pixel_size(project_id, page_index, crop)
    mm_per_px, span_w, span_h, xs, ys, suggested, notes = _calibrate_mm_per_px(
        project_id, page_index, crop, crop_w, crop_h, scale_note=scale_note
    )

    x_lines_px: list[float] = []
    y_lines_px: list[float] = []
    mm_x: float | None = None
    mm_y: float | None = None
    if xs and ys and len(xs) >= 2 and len(ys) >= 2:
        x_lines_px, y_lines_px, xs, ys, mm_x, mm_y, grid_notes = _build_aligned_grid_px(
            project_id,
            page_index,
            crop,
            crop_w,
            crop_h,
            xs,
            ys,
            scale_note=scale_note,
        )
        span_w = xs[-1] if xs else span_w
        span_h = ys[-1] if ys else span_h
        notes.extend(grid_notes)
        if x_lines_px and y_lines_px:
            notes.append(
                f"Grid overlay: {len(x_lines_px)} X × {len(y_lines_px)} Y (labels+vectors)."
            )

    mm_per_px_x = mm_x
    mm_per_px_y = mm_y
    if mm_per_px_x and not mm_per_px:
        mm_per_px = mm_per_px_x

    return {
        "crop_width_px": crop_w,
        "crop_height_px": crop_h,
        "mm_per_px": mm_per_px,
        "mm_per_px_x": mm_per_px_x,
        "mm_per_px_y": mm_per_px_y,
        "span_width_mm": span_w,
        "span_height_mm": span_h,
        "x_grid_positions_mm": xs,
        "y_grid_positions_mm": ys,
        "grid_lines_x_px": x_lines_px,
        "grid_lines_y_px": y_lines_px,
        "grid_lines_x_pt": [],
        "grid_lines_y_pt": [],
        "crop_bounds_pt": None,
        "vector_grid_source": "axis_labels_and_vectors",
        "suggested_column_profile": suggested,
        "notes": notes,
    }


def _stations_from_clicks(
    clicks: list[ColumnClick],
    crop_width_px: int,
    crop_height_px: int,
    mm_per_px: float,
) -> tuple[list[float], list[float]]:
    """Fallback bays: cluster click axes, spacing from pixel deltas × mm/px."""
    xs_px = _cluster_axis_px([c.x_px for c in clicks], crop_width_px)
    ys_px = _cluster_axis_px([c.y_px for c in clicks], crop_height_px)
    if not xs_px or not ys_px:
        return [], []
    x0, y0 = xs_px[0], ys_px[0]
    xs_mm = [_px_to_mm(x, x0, mm_per_px) for x in xs_px]
    ys_mm = [_px_to_mm(y, y0, mm_per_px) for y in ys_px]
    return _normalize_axis_positions(xs_mm), _normalize_axis_positions(ys_mm)


def _click_norm(
    click: ColumnClick,
    crop_width_px: int,
    crop_height_px: int,
) -> tuple[float, float]:
    if click.x_norm is not None and click.y_norm is not None:
        return click.x_norm, click.y_norm
    w = max(crop_width_px, 1)
    h = max(crop_height_px, 1)
    return click.x_px / w, click.y_px / h


def analysis_from_column_clicks(
    clicks: list[ColumnClick],
    *,
    crop_width_px: int,
    crop_height_px: int,
    mm_per_px: float | None = None,
    span_width_mm: float | None = None,
    span_height_mm: float | None = None,
    x_grid_positions_mm: list[float] | None = None,
    y_grid_positions_mm: list[float] | None = None,
    grid_lines_x_pt: list[float] | None = None,
    grid_lines_y_pt: list[float] | None = None,
    grid_lines_x_px: list[float] | None = None,
    grid_lines_y_px: list[float] | None = None,
    crop_bounds_pt: dict | None = None,
    column_profile: str = "HEB200",
    height_mm: float = 6000.0,
) -> RegionStructuralAnalysis:
    if len(clicks) < _MIN_CLICKS:
        raise ValueError("Add at least one column click on the plan.")

    xs_mm = _normalize_axis_positions(list(x_grid_positions_mm or []))
    ys_mm = _normalize_axis_positions(list(y_grid_positions_mm or []))

    scale = mm_per_px if mm_per_px and mm_per_px > 0 else None
    if not _valid_pdf_stations(xs_mm) or not _valid_pdf_stations(ys_mm):
        if scale:
            xs_mm, ys_mm = _stations_from_clicks(
                clicks, crop_width_px, crop_height_px, scale
            )
        else:
            xs_px = _cluster_axis_px([c.x_px for c in clicks], crop_width_px)
            ys_px = _cluster_axis_px([c.y_px for c in clicks], crop_height_px)
            xs_mm = [float(i) for i in range(len(xs_px))]
            ys_mm = [float(i) for i in range(len(ys_px))]

    if not _valid_pdf_stations(xs_mm) or not _valid_pdf_stations(ys_mm):
        raise ValueError("Could not build grid stations — add more columns or use a clearer crop.")

    span_x = xs_mm[-1] if xs_mm else (span_width_mm or 0.0)
    span_y = ys_mm[-1] if ys_mm else (span_height_mm or 0.0)
    mm_x = (span_x / crop_width_px) if span_x and crop_width_px > 0 else scale
    mm_y = (span_y / crop_height_px) if span_y and crop_height_px > 0 else mm_x
    use_pdf_snap = bool(mm_x and mm_y and span_x > 0 and span_y > 0)
    extraction_source = (
        "column_clicks_pdf_grid_snap" if use_pdf_snap else "column_clicks_exact_mm"
    )

    from analyzer_service.region_grid_lines import _dedupe_lines

    have_pdf_stations = _valid_pdf_stations(
        _normalize_axis_positions(list(x_grid_positions_mm or []))
    ) and _valid_pdf_stations(_normalize_axis_positions(list(y_grid_positions_mm or [])))

    x_lines_px = _dedupe_lines(list(grid_lines_x_px or []))
    y_lines_px = _dedupe_lines(list(grid_lines_y_px or []))
    if len(x_lines_px) < 2 or len(y_lines_px) < 2:
        if have_pdf_stations and span_x > 0 and span_y > 0:
            x_lines_px = _dedupe_lines(
                [(x / span_x) * crop_width_px for x in xs_mm]
            )
            y_lines_px = _dedupe_lines(
                [
                    crop_height_px - (y / span_y) * crop_height_px
                    for y in ys_mm
                ]
            )
        else:
            x_lines_px = _dedupe_lines(
                _cluster_axis_px([c.x_px for c in clicks], crop_width_px)
            )
            y_lines_px = _dedupe_lines(
                _cluster_axis_px([c.y_px for c in clicks], crop_height_px)
            )
    mm_x = mm_x or scale
    mm_y = mm_y or scale
    if not have_pdf_stations:
        if x_lines_px and mm_x:
            xs_mm = [round(x * mm_x, 1) for x in sorted(x_lines_px)]
        if y_lines_px and mm_y:
            ys_mm = [
                round((crop_height_px - y) * mm_y, 1) for y in sorted(y_lines_px)
            ]
    snap_in_px = (
        use_pdf_snap
        and not have_pdf_stations
        and len(x_lines_px) >= 2
        and len(y_lines_px) >= 2
    )

    placements: list[ColumnPlacement] = []
    for i, click in enumerate(clicks):
        if snap_in_px:
            ix = _nearest_index(click.x_px, sorted(x_lines_px))
            iy = _nearest_index(click.y_px, sorted(y_lines_px))
            ix = min(ix, len(xs_mm) - 1)
            iy = min(iy, len(ys_mm) - 1)
            x_mm = round(float(xs_mm[ix]), 1)
            y_mm = round(float(ys_mm[iy]), 1)
            col_id = f"col_{i}"
        elif use_pdf_snap and mm_x and mm_y:
            x_query = click.x_px * mm_x
            y_query = span_y - click.y_px * mm_y
            ix = _nearest_index(x_query, xs_mm)
            iy = _nearest_index(y_query, ys_mm)
            x_mm = round(float(xs_mm[ix]), 1)
            y_mm = round(float(ys_mm[iy]), 1)
            col_id = f"col_{ix}_{iy}"
        elif scale and scale > 0:
            x_mm = round(click.x_px * scale, 1)
            y_mm = round(click.y_px * scale, 1)
            col_id = f"col_{i}"
        elif span_width_mm and crop_width_px > 0:
            x_norm, y_norm = _click_norm(click, crop_width_px, crop_height_px)
            x_mm = round(x_norm * span_width_mm, 1)
            y_span = span_height_mm or span_y or span_width_mm
            y_mm = round(y_norm * y_span, 1) if crop_height_px > 0 else 0.0
            col_id = f"col_{i}"
        else:
            x_mm = round(float(click.x_px), 1)
            y_mm = round(float(click.y_px), 1)
            col_id = f"col_{i}"

        mark = (click.mark or "").strip() or f"C{i + 1}"
        placements.append(
            ColumnPlacement(
                id=col_id,
                x_mm=x_mm,
                y_mm=y_mm,
                profile_name=column_profile,
                height_mm=height_mm,
                mark=mark,
            )
        )

    x_text = ", ".join(str(int(v) if v == int(v) else v) for v in xs_mm)
    y_text = ", ".join(str(int(v) if v == int(v) else v) for v in ys_mm)

    return RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        layout_mode="dense_matrix",
        x_grid_positions_mm=xs_mm,
        y_grid_positions_mm=ys_mm,
        column_placements=placements,
        active_column_intersections=[],
        detected_parameters=[
            DetectedParameterEntry(key="column_profile", value=column_profile),
            DetectedParameterEntry(key="grid_lines_x_mm", value=x_text),
            DetectedParameterEntry(key="grid_lines_y_mm", value=y_text),
            DetectedParameterEntry(
                key="grid_extraction_source",
                value=extraction_source,
            ),
            DetectedParameterEntry(key="column_height_mm", value=str(int(height_mm))),
        ],
    )

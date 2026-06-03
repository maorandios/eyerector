"""
Extract grid stations from PDF vector/text inside a plan-crop region.

Used before/alongside vision so dimension chains come from the drawing, not LLM guesses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import fitz

from analyzer_service.pdf_extract.vector_geometry import _infer_mm_per_unit, _segments_from_path
from analyzer_service.pdf_project_storage import project_dir
from analyzer_service.region_analysis_schemas import (
    ActiveColumnIntersection,
    CropRectNorm,
    DetectedParameterEntry,
    RegionStructuralAnalysis,
)
from analyzer_service.region_layout_compiler import (
    STATION_TOL_MM,
    _best_axis_candidate,
    _normalize_axis_positions,
    _positions_from_bay_spacings,
)

_DIM_NUMBER_RE = re.compile(r"\b(\d{2,5}(?:\.\d+)?)\b")
_MIN_DIM_MM = 20.0
_MAX_DIM_MM = 120_000.0
_BAND_FRAC = 0.22
_MIN_STATIONS = 3
_MAX_STATIONS = 32
_MERGE_MIN_CONFIDENCE = 0.35
_MIN_BAY_MM = 40.0
_MAX_BAY_MM = 25_000.0


@dataclass
class PdfGridExtraction:
    x_stations_mm: list[float] = field(default_factory=list)
    y_stations_mm: list[float] = field(default_factory=list)
    x_bays_mm: list[float] = field(default_factory=list)
    y_bays_mm: list[float] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "none"
    notes: list[str] = field(default_factory=list)


def parse_crop_rect_norm(raw: str | None) -> CropRectNorm | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
        return CropRectNorm.model_validate(data)
    except Exception:
        return None


def _fitz_page_index(page_index: int) -> int:
    """API/manifest page_index is 1-based; fitz uses 0-based."""
    return max(0, page_index - 1) if page_index > 0 else 0


def _clip_rect(page: fitz.Page, crop: CropRectNorm) -> fitz.Rect:
    r = page.rect
    x0 = r.x0 + crop.x * r.width
    y0 = r.y0 + crop.y * r.height
    x1 = x0 + crop.w * r.width
    y1 = y0 + crop.h * r.height
    return fitz.Rect(x0, y0, x1, y1)


def _pt_to_crop_mm(x_pt: float, y_pt: float, clip: fitz.Rect, mm_per_pt: float) -> tuple[float, float]:
    """Crop-local mm: origin bottom-left, +X right, +Y up."""
    x_mm = (x_pt - clip.x0) * mm_per_pt
    y_mm = (clip.y1 - y_pt) * mm_per_pt
    return x_mm, y_mm


def _parse_dimension_numbers(text: str) -> list[float]:
    out: list[float] = []
    for m in _DIM_NUMBER_RE.finditer(text):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if _MIN_DIM_MM <= v <= _MAX_DIM_MM:
            out.append(v)
    return out


def _valid_station_chain(stations: list[float]) -> bool:
    if len(stations) < 2 or len(stations) > _MAX_STATIONS:
        return False
    if stations[0] > 80.0:
        return False
    bays = [stations[i] - stations[i - 1] for i in range(1, len(stations))]
    if not bays:
        return False
    bad = sum(1 for b in bays if b < _MIN_BAY_MM or b > _MAX_BAY_MM)
    return bad <= max(1, int(len(bays) * 0.2))


def _chain_to_stations(numbers: list[float]) -> tuple[list[float], list[float]]:
    """Return (cumulative stations, bay widths) from ordered dimension numbers."""
    if len(numbers) < 2:
        return [], []
    normalized = _normalize_axis_positions(numbers)
    if len(normalized) >= 2 and normalized[0] <= STATION_TOL_MM:
        bays = [
            normalized[i] - normalized[i - 1]
            for i in range(1, len(normalized))
            if normalized[i] - normalized[i - 1] > STATION_TOL_MM
        ]
        return normalized, bays
    bays = [float(v) for v in numbers if v > STATION_TOL_MM]
    if len(bays) >= 2:
        stations = _normalize_axis_positions(_positions_from_bay_spacings(bays))
        return stations, bays
    return normalized, []


def _text_spans_in_clip(page: fitz.Page, clip: fitz.Rect) -> list[tuple[float, float, float, float, str]]:
    """(x0, y0, x1, y1, text) for spans intersecting clip."""
    spans: list[tuple[float, float, float, float, str]] = []
    try:
        blocks = page.get_text("dict", clip=clip).get("blocks", [])
    except Exception:
        return spans
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text", "")).strip()
                if not text:
                    continue
                bbox = span.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                x0, y0, x1, y1 = (float(bbox[i]) for i in range(4))
                cx = (x0 + x1) / 2.0
                cy = (y0 + y1) / 2.0
                if clip.x0 <= cx <= clip.x1 and clip.y0 <= cy <= clip.y1:
                    spans.append((x0, y0, x1, y1, text))
    return spans


def _numbers_along_edge(
    spans: list[tuple[float, float, float, float, str]],
    clip: fitz.Rect,
    edge: str,
) -> list[float]:
    """Collect dimension numbers near crop edges (bottom/top/left/right)."""
    band_x = _BAND_FRAC * clip.width
    band_y = _BAND_FRAC * clip.height
    picked: list[tuple[float, float]] = []

    for x0, y0, x1, y1, text in spans:
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        if edge == "bottom" and cy < clip.y1 - band_y:
            continue
        if edge == "top" and cy > clip.y0 + band_y:
            continue
        if edge == "left" and cx > clip.x0 + band_x:
            continue
        if edge == "right" and cx < clip.x1 - band_x:
            continue
        if edge in ("bottom", "top"):
            sort_key = cx
        else:
            # PDF Y grows downward; reverse for bottom-to-top structural order on left/right.
            sort_key = -cy
        for v in _parse_dimension_numbers(text):
            picked.append((sort_key, v))

    picked.sort(key=lambda t: t[0])
    ordered: list[float] = []
    seen: set[float] = set()
    for _, v in picked:
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


def _dimension_numbers_primary_row(
    spans: list[tuple[float, float, float, float, str]],
    clip: fitz.Rect,
    *,
    axis: str,
) -> list[float]:
    """
    One dimension string row along the crop edge (bottom for X, left for Y).
    Avoids picking random numbers from inside the plan.
    """
    band = 0.12 * (clip.height if axis == "x" else clip.width)
    in_band: list[tuple[float, float, str]] = []
    for x0, y0, x1, y1, text in spans:
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        if axis == "x":
            if cy < clip.y1 - band:
                continue
            sort_key = cx
            row_key = cy
        else:
            if cx > clip.x0 + band:
                continue
            sort_key = -cy
            row_key = cx
        if _parse_dimension_numbers(text):
            in_band.append((row_key, sort_key, text))

    if not in_band:
        return []

    # Keep the outermost dimension row (bottom for X, left for Y).
    if axis == "x":
        target_row = max(t[0] for t in in_band)
        row_tol = band * 0.5
        row_items = [t for t in in_band if t[0] >= target_row - row_tol]
    else:
        target_row = min(t[0] for t in in_band)
        row_tol = band * 0.5
        row_items = [t for t in in_band if t[0] <= target_row + row_tol]

    row_items.sort(key=lambda t: t[1])
    nums: list[float] = []
    for _, _, text in row_items:
        nums.extend(_parse_dimension_numbers(text))
    return nums


def _best_chain_from_edges(spans: list[tuple[float, float, float, float, str]], clip: fitz.Rect, axis: str) -> tuple[list[float], list[float]]:
    """Primary row on bottom (X) or left (Y); fallback to opposite edge."""
    if axis == "x":
        order = ("bottom", "top")
    else:
        order = ("left", "right")

    candidates: list[tuple[list[float], list[float]]] = []
    primary_nums = _dimension_numbers_primary_row(spans, clip, axis=axis)
    if primary_nums:
        candidates.append(_chain_to_stations(primary_nums))
    for edge in order:
        stations, bays = _chain_to_stations(_numbers_along_edge(spans, clip, edge))
        if stations:
            candidates.append((stations, bays))

    best_stations: list[float] = []
    best_bays: list[float] = []
    for stations, bays in candidates:
        if not _valid_station_chain(stations):
            continue
        if len(stations) > len(best_stations):
            best_stations, best_bays = stations, bays
    return best_stations, best_bays


def _cluster_line_positions(
    segments: list[tuple[float, float, float, float]],
    *,
    vertical: bool,
    mm_per_pt: float,
    clip: fitz.Rect,
    tol_mm: float = 35.0,
) -> list[float]:
    coords_mm: list[float] = []
    for x1, y1, x2, y2 in segments:
        if vertical:
            if abs(x2 - x1) > 8.0:
                continue
            x_pt = (x1 + x2) / 2.0
            length_pt = abs(y2 - y1)
            if length_pt < 40.0:
                continue
            x_mm, _ = _pt_to_crop_mm(x_pt, clip.y0, clip, mm_per_pt)
            coords_mm.append(x_mm)
        else:
            if abs(y2 - y1) > 8.0:
                continue
            y_pt = (y1 + y2) / 2.0
            length_pt = abs(x2 - x1)
            if length_pt < 40.0:
                continue
            _, y_mm = _pt_to_crop_mm(clip.x0, y_pt, clip, mm_per_pt)
            coords_mm.append(y_mm)

    if not coords_mm:
        return []

    coords_mm.sort()
    clusters: list[list[float]] = []
    for v in coords_mm:
        if not clusters or v - clusters[-1][-1] > tol_mm:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return [sum(c) / len(c) for c in clusters]


def _vector_grid_stations(
    page: fitz.Page,
    clip: fitz.Rect,
    mm_per_pt: float,
) -> tuple[list[float], list[float]]:
    vertical: list[tuple[float, float, float, float]] = []
    horizontal: list[tuple[float, float, float, float]] = []
    try:
        for path in page.get_drawings():
            for seg in _segments_from_path(path, 0):
                mid_x = (seg.x1 + seg.x2) / 2.0
                mid_y = (seg.y1 + seg.y2) / 2.0
                if not (clip.x0 <= mid_x <= clip.x1 and clip.y0 <= mid_y <= clip.y1):
                    continue
                if abs(seg.x2 - seg.x1) <= 8.0:
                    vertical.append((seg.x1, seg.y1, seg.x2, seg.y2))
                elif abs(seg.y2 - seg.y1) <= 8.0:
                    horizontal.append((seg.x1, seg.y1, seg.x2, seg.y2))
    except Exception:
        return [], []

    xs = _cluster_line_positions(vertical, vertical=True, mm_per_pt=mm_per_pt, clip=clip)
    ys = _cluster_line_positions(horizontal, vertical=False, mm_per_pt=mm_per_pt, clip=clip)
    xs = _normalize_axis_positions([0.0, *xs] if xs and xs[0] > STATION_TOL_MM else xs)
    ys = _normalize_axis_positions([0.0, *ys] if ys and ys[0] > STATION_TOL_MM else ys)
    return xs, ys


def extract_region_grid_from_pdf(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
    *,
    scale_note: str | None = None,
) -> PdfGridExtraction | None:
    pdf_path = project_dir(project_id) / "source.pdf"
    if not pdf_path.is_file():
        return None

    doc = fitz.open(pdf_path)
    try:
        idx = _fitz_page_index(page_index)
        if idx >= doc.page_count:
            return None
        page = doc[idx]
        clip = _clip_rect(page, crop)

        spans = _text_spans_in_clip(page, clip)
        x_stations, x_bays = _best_chain_from_edges(spans, clip, "x")
        y_stations, y_bays = _best_chain_from_edges(spans, clip, "y")

        coords = [clip.x0, clip.x1, clip.y0, clip.y1]
        segments_for_scale: list = []
        try:
            for path in page.get_drawings():
                segments_for_scale.extend(_segments_from_path(path, 0))
        except Exception:
            pass
        mm_per_pt = _infer_mm_per_unit(coords, segments_for_scale, scale_note)
        vx, vy = _vector_grid_stations(page, clip, mm_per_pt)
        vx = vx if _valid_station_chain(vx) else []
        vy = vy if _valid_station_chain(vy) else []

        x_final = x_stations if _valid_station_chain(x_stations) else []
        y_final = y_stations if _valid_station_chain(y_stations) else []
        if not x_final and _valid_station_chain(vx):
            x_final = vx
        if not y_final and _valid_station_chain(vy):
            y_final = vy
        if x_final and vx and len(vx) >= len(x_final) and abs(vx[-1] - x_final[-1]) < 500:
            x_final = _best_axis_candidate(x_final, vx)
        if y_final and vy and len(vy) >= len(y_final) and abs(vy[-1] - y_final[-1]) < 500:
            y_final = _best_axis_candidate(y_final, vy)

        notes: list[str] = []
        source_parts: list[str] = []
        if len(x_stations) >= _MIN_STATIONS:
            source_parts.append("text_x")
        if len(y_stations) >= _MIN_STATIONS:
            source_parts.append("text_y")
        if len(vx) >= _MIN_STATIONS:
            source_parts.append("vector_x")
        if len(vy) >= _MIN_STATIONS:
            source_parts.append("vector_y")

        if len(x_final) < 2 and len(y_final) < 2:
            return PdfGridExtraction(
                confidence=0.0,
                source="none",
                notes=["PDF grid: no dimension text or grid lines found in crop."],
            )

        confidence = 0.55
        if len(x_final) >= _MIN_STATIONS:
            confidence += 0.2
        if len(y_final) >= _MIN_STATIONS:
            confidence += 0.2
        if source_parts:
            confidence = min(0.95, confidence + 0.05 * len(source_parts))

        notes.append(
            f"PDF grid ({', '.join(source_parts) or 'partial'}): "
            f"X={len(x_final)} lines, Y={len(y_final)} lines."
        )

        return PdfGridExtraction(
            x_stations_mm=x_final,
            y_stations_mm=y_final,
            x_bays_mm=x_bays,
            y_bays_mm=y_bays,
            confidence=confidence,
            source="pdf_hybrid",
            notes=notes,
        )
    finally:
        doc.close()


def _reindex_intersections(
    intersections: list[ActiveColumnIntersection],
    old_xs: list[float],
    old_ys: list[float],
    new_xs: list[float],
    new_ys: list[float],
) -> list[ActiveColumnIntersection]:
    if not intersections or not new_xs or not new_ys:
        return intersections

    def nearest_index(stations: list[float], idx: int, old: list[float]) -> int:
        if idx < len(old):
            target = old[idx]
        elif stations and idx < len(stations):
            return idx
        else:
            return min(idx, len(stations) - 1)
        return min(range(len(stations)), key=lambda i: abs(stations[i] - target))

    out: list[ActiveColumnIntersection] = []
    for hit in intersections:
        ix = nearest_index(new_xs, hit.grid_index_x, old_xs)
        iy = nearest_index(new_ys, hit.grid_index_y, old_ys)
        if ix < 0 or ix >= len(new_xs) or iy < 0 or iy >= len(new_ys):
            continue
        out.append(
            hit.model_copy(
                update={
                    "grid_index_x": ix,
                    "grid_index_y": iy,
                }
            )
        )
    return out


def _prefer_pdf_axis(pdf_axis: list[float], vision_axis: list[float]) -> list[float]:
    pdf_ok = _valid_station_chain(pdf_axis)
    vis_ok = _valid_station_chain(vision_axis)
    if pdf_ok and not vis_ok:
        return pdf_axis
    if vis_ok and not pdf_ok:
        return vision_axis
    if not pdf_ok and not vis_ok:
        return vision_axis if len(vision_axis) >= 2 else pdf_axis
    # Vision often returns only [0, total]; PDF dimension row is more complete.
    if len(vision_axis) <= 2 and len(pdf_axis) >= 3:
        return pdf_axis
    # PDF polluted with inner/vector noise (too many lines).
    if len(pdf_axis) > len(vision_axis) + 2 and len(pdf_axis) > 14:
        return vision_axis
    if len(pdf_axis) > len(vision_axis):
        return pdf_axis
    return vision_axis


def merge_pdf_grid_into_analysis(
    analysis: RegionStructuralAnalysis,
    pdf: PdfGridExtraction,
) -> RegionStructuralAnalysis:
    """Prefer PDF-derived stations when richer than vision; keep sparse columns from vision."""
    if len(pdf.x_stations_mm) < 2 and len(pdf.y_stations_mm) < 2:
        return analysis
    if pdf.confidence < _MERGE_MIN_CONFIDENCE and max(len(pdf.x_stations_mm), len(pdf.y_stations_mm)) < _MIN_STATIONS:
        return analysis

    old_xs = list(analysis.x_grid_positions_mm)
    old_ys = list(analysis.y_grid_positions_mm)

    new_xs = _prefer_pdf_axis(pdf.x_stations_mm, old_xs)
    new_ys = _prefer_pdf_axis(pdf.y_stations_mm, old_ys)

    if len(new_xs) < 2 and len(old_xs) >= 2:
        new_xs = old_xs
    if len(new_ys) < 2 and len(old_ys) >= 2:
        new_ys = old_ys

    active = list(analysis.active_column_intersections)
    if active and new_xs and new_ys:
        active = _reindex_intersections(active, old_xs, old_ys, new_xs, new_ys)

    entries = [e for e in analysis.detected_parameters if e.key not in (
        "grid_lines_x_mm",
        "grid_lines_y_mm",
        "grid_extraction_source",
    )]
    if new_xs:
        x_text = ", ".join(str(int(v)) if v == int(v) else str(round(v, 1)) for v in new_xs)
        entries.append(DetectedParameterEntry(key="grid_lines_x_mm", value=x_text))
    if new_ys:
        y_text = ", ".join(str(int(v)) if v == int(v) else str(round(v, 1)) for v in new_ys)
        entries.append(DetectedParameterEntry(key="grid_lines_y_mm", value=y_text))
    entries.append(
        DetectedParameterEntry(
            key="grid_extraction_source",
            value=f"{pdf.source};conf={pdf.confidence:.2f}",
        )
    )

    notes = analysis.notes or ""
    pdf_note = " ".join(pdf.notes)
    if pdf_note and pdf_note not in notes:
        notes = f"{notes} {pdf_note}".strip()

    element_type = analysis.element_type
    if (len(new_xs) >= 2 and len(new_ys) >= 2) and element_type in ("unknown", "truss", "mezzanine"):
        element_type = "grid"

    return analysis.model_copy(
        update={
            "element_type": element_type,
            "x_grid_positions_mm": new_xs,
            "y_grid_positions_mm": new_ys,
            "x_bay_spacings_mm": pdf.x_bays_mm or analysis.x_bay_spacings_mm,
            "y_bay_spacings_mm": pdf.y_bays_mm or analysis.y_bay_spacings_mm,
            "active_column_intersections": active,
            "detected_parameters": entries,
            "layout_mode": analysis.layout_mode
            if active
            else analysis.layout_mode,
            "notes": notes or None,
        }
    )

"""
Geometry-first grid for plan-crop: PDF vectors → crop pixel lines → SVG vertices.

Used for interactive snap-to-vertex column placement (no mm guessing in the overlay).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

from analyzer_service.pdf_extract.vector_geometry import _infer_mm_per_unit, _segments_from_path
from analyzer_service.pdf_project_storage import load_manifest, project_dir
from analyzer_service.region_analysis_schemas import (
    ActiveColumnIntersection,
    CropRectNorm,
    DetectedParameterEntry,
    RegionStructuralAnalysis,
)
from analyzer_service.region_pdf_grid import (
    _clip_rect,
    _fitz_page_index,
    _text_spans_in_clip,
    extract_region_grid_from_pdf,
    parse_crop_rect_norm,
)

_MIN_LINES_PER_AXIS = 2
_MAX_LINES_PER_AXIS = 48
_COLUMN_MARK_RE = re.compile(r"^C\s*(\d+)\s*$", re.IGNORECASE)


@dataclass
class GridVertex:
    grid_index_x: int
    grid_index_y: int
    x_px: float
    y_px: float


@dataclass
class RegionGridGeometry:
    crop_width_px: int
    crop_height_px: int
    x_lines_px: list[float] = field(default_factory=list)
    y_lines_px: list[float] = field(default_factory=list)
    vertices: list[GridVertex] = field(default_factory=list)
    mm_per_px: float | None = None
    span_width_mm: float | None = None
    span_height_mm: float | None = None
    source: str = "pdf_vectors"
    notes: list[str] = field(default_factory=list)


def _crop_pixel_size(project_id: str, page_index: int, crop: CropRectNorm) -> tuple[int, int]:
    manifest = load_manifest(project_id)
    page = next((p for p in manifest.get("pages", []) if p.get("page_index") == page_index), None)
    if not page:
        return (800, 600)
    w = max(1, int(page.get("width_px", 800)))
    h = max(1, int(page.get("height_px", 600)))
    return (
        max(1, int(round(crop.w * w))),
        max(1, int(round(crop.h * h))),
    )


def crop_pixel_size_from_pdf_render(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
) -> tuple[int, int]:
    """
    Crop size matching page PNG crop (same DPI as upload render).
    Prefer over manifest math when aligning vectors to the browser crop image.
    """
    from analyzer_service.pdf_project_storage import _project_dpi, project_dir
    from analyzer_service.region_pdf_grid import _clip_rect, _fitz_page_index

    pdf_path = project_dir(project_id) / "source.pdf"
    if not pdf_path.is_file():
        return _crop_pixel_size(project_id, page_index, crop)
    doc = fitz.open(pdf_path)
    try:
        idx = _fitz_page_index(page_index)
        if idx >= doc.page_count:
            return _crop_pixel_size(project_id, page_index, crop)
        page = doc[idx]
        clip = _clip_rect(page, crop)
        dpi = _project_dpi()
        scale = dpi / 72.0
        pix = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            clip=clip,
            alpha=False,
        )
        return max(1, pix.width), max(1, pix.height)
    except Exception:
        return _crop_pixel_size(project_id, page_index, crop)
    finally:
        doc.close()


def _pt_to_crop_px(
    x_pt: float,
    y_pt: float,
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
) -> tuple[float, float]:
    """PDF clip → crop image pixels (origin top-left, y down — matches browser canvas)."""
    x_px = (x_pt - clip.x0) / max(clip.width, 1.0) * crop_w
    y_px = (y_pt - clip.y0) / max(clip.height, 1.0) * crop_h
    return x_px, y_px


def _cluster_coords(values: list[float], tol: float) -> list[float]:
    if not values:
        return []
    values = sorted(values)
    clusters: list[list[float]] = []
    for v in values:
        if not clusters or v - clusters[-1][-1] > tol:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return [sum(c) / len(c) for c in clusters]


def _cluster_weighted(samples: list[tuple[float, float]], tol: float) -> list[float]:
    """Cluster (coord, weight) pairs; return weighted centroids."""
    if not samples:
        return []
    samples = sorted(samples, key=lambda t: t[0])
    clusters: list[list[tuple[float, float]]] = []
    for coord, weight in samples:
        if not clusters or coord - clusters[-1][-1][0] > tol:
            clusters.append([(coord, weight)])
        else:
            clusters[-1].append((coord, weight))
    out: list[float] = []
    for cluster in clusters:
        total_w = sum(w for _, w in cluster) or 1.0
        out.append(sum(c * w for c, w in cluster) / total_w)
    return out


def _seg_intersects_clip(x1: float, y1: float, x2: float, y2: float, clip: fitz.Rect) -> bool:
    left = max(min(x1, x2), clip.x0)
    right = min(max(x1, x2), clip.x1)
    top = max(min(y1, y2), clip.y0)
    bottom = min(max(y1, y2), clip.y1)
    return right >= left and bottom >= top


def _mm_stations_to_px(
    stations_mm: list[float],
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
    mm_per_pt: float,
    *,
    vertical: bool,
) -> list[float]:
    crop_span_mm = (clip.width if vertical else clip.height) * mm_per_pt
    if crop_span_mm <= 0:
        return []
    crop_span_px = crop_w if vertical else crop_h
    return [round(s / crop_span_mm * crop_span_px, 2) for s in stations_mm]


def _merge_line_positions(
    *line_sets: list[float],
    tol_px: float,
    max_lines: int = _MAX_LINES_PER_AXIS,
) -> list[float]:
    merged: list[float] = []
    for lines in line_sets:
        merged.extend(lines)
    if not merged:
        return []
    clustered = _cluster_coords(merged, tol_px)
    if len(clustered) <= max_lines:
        return clustered
    # Too many lines: keep strongest clusters by spacing (drop isolated noise).
    clustered = sorted(clustered)
    gaps = [clustered[i] - clustered[i - 1] for i in range(1, len(clustered))]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else tol_px * 2
    min_sep = max(tol_px * 0.75, median_gap * 0.35)
    trimmed: list[float] = []
    for x in clustered:
        if not trimmed or x - trimmed[-1] >= min_sep:
            trimmed.append(x)
    return trimmed[:max_lines]


def _expand_lines_for_points(
    lines: list[float],
    points: list[float],
    tol_px: float,
) -> list[float]:
    """Add axis lines at column centers that are not near an existing line."""
    extra = [p for p in points if not any(abs(p - line) <= tol_px for line in lines)]
    if not extra:
        return lines
    return sorted(_cluster_coords([*lines, *extra], tol_px))


def _column_mark_centers_px(
    page: fitz.Page,
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
) -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    for x0, y0, x1, y1, text in _text_spans_in_clip(page, clip):
        if not _COLUMN_MARK_RE.match(text.strip()):
            continue
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        x_px, y_px = _pt_to_crop_px(cx, cy, clip, crop_w, crop_h)
        centers.append((x_px, y_px))
    return centers


def _extract_line_positions_px(
    page: fitz.Page,
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
    *,
    mm_per_pt: float,
) -> tuple[list[float], list[float], list[tuple[float, float]]]:
    """
    Multi-pass vector extraction: long grid lines + short ticks + dimension/mm hints.
    Returns (x_lines_px, y_lines_px, column_centers_px).
    """
    tol_px = max(6.0, min(crop_w, crop_h) * 0.004)
    min_long_v = max(25.0, clip.height * 0.12)
    min_long_h = max(25.0, clip.width * 0.12)
    min_short = max(12.0, min(clip.width, clip.height) * 0.02)

    x_samples: list[tuple[float, float]] = []
    y_samples: list[tuple[float, float]] = []

    try:
        for path in page.get_drawings():
            for seg in _segments_from_path(path, 0):
                if not _seg_intersects_clip(seg.x1, seg.y1, seg.x2, seg.y2, clip):
                    continue
                length = seg.length()
                dx = abs(seg.x2 - seg.x1)
                dy = abs(seg.y2 - seg.y1)

                if dx <= 8.0 and length >= min_short:
                    for x_pt in (seg.x1, seg.x2):
                        if clip.x0 <= x_pt <= clip.x1:
                            x_px, _ = _pt_to_crop_px(x_pt, clip.y0, clip, crop_w, crop_h)
                            weight = length if length >= min_long_v else length * 0.6
                            x_samples.append((x_px, weight))
                elif dy <= 8.0 and length >= min_short:
                    for y_pt in (seg.y1, seg.y2):
                        if clip.y0 <= y_pt <= clip.y1:
                            _, y_px = _pt_to_crop_px(clip.x0, y_pt, clip, crop_w, crop_h)
                            weight = length if length >= min_long_h else length * 0.6
                            y_samples.append((y_px, weight))
    except Exception:
        pass

    x_lines = _cluster_weighted(x_samples, tol_px)
    y_lines = _cluster_weighted(y_samples, tol_px)
    column_centers = _column_mark_centers_px(page, clip, crop_w, crop_h)
    return x_lines, y_lines, column_centers


def _span_from_pdf_text(page: fitz.Page, clip: fitz.Rect) -> tuple[float | None, float | None]:
    """Rough max span hints from dimension numbers in crop (mm)."""
    import re

    nums: list[float] = []
    try:
        text = page.get_text("text", clip=clip) or ""
    except Exception:
        return None, None
    for m in re.finditer(r"\b(\d{3,5})\b", text):
        try:
            v = float(m.group(1))
            if 500 <= v <= 120_000:
                nums.append(v)
        except ValueError:
            continue
    if not nums:
        return None, None
    return max(nums), max(nums)


def extract_region_grid_geometry(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
    *,
    scale_note: str | None = None,
) -> RegionGridGeometry | None:
    pdf_path = project_dir(project_id) / "source.pdf"
    if not pdf_path.is_file():
        return None

    crop_w, crop_h = _crop_pixel_size(project_id, page_index, crop)
    doc = fitz.open(pdf_path)
    try:
        idx = _fitz_page_index(page_index)
        if idx >= doc.page_count:
            return None
        page = doc[idx]
        clip = _clip_rect(page, crop)

        segments_for_scale: list = []
        try:
            for path in page.get_drawings():
                segments_for_scale.extend(_segments_from_path(path, 0))
        except Exception:
            pass
        mm_per_pt = _infer_mm_per_unit(
            [clip.x0, clip.x1, clip.y0, clip.y1], segments_for_scale, scale_note
        )

        x_vec, y_vec, column_centers = _extract_line_positions_px(
            page, clip, crop_w, crop_h, mm_per_pt=mm_per_pt
        )
        tol_px = max(6.0, min(crop_w, crop_h) * 0.004)
        notes: list[str] = []

        pdf_x_px: list[float] = []
        pdf_y_px: list[float] = []
        pdf_grid = extract_region_grid_from_pdf(
            project_id, page_index, crop, scale_note=scale_note
        )
        if pdf_grid and pdf_grid.confidence >= 0.35:
            pdf_x_px = _mm_stations_to_px(
                pdf_grid.x_stations_mm, clip, crop_w, crop_h, mm_per_pt, vertical=True
            )
            pdf_y_px = _mm_stations_to_px(
                pdf_grid.y_stations_mm, clip, crop_w, crop_h, mm_per_pt, vertical=False
            )
            if pdf_x_px or pdf_y_px:
                notes.append(
                    f"Merged PDF dimension grid (conf={pdf_grid.confidence:.2f})."
                )

        col_x = [c[0] for c in column_centers]
        col_y = [c[1] for c in column_centers]
        x_lines = _merge_line_positions(x_vec, pdf_x_px, tol_px=tol_px)
        y_lines = _merge_line_positions(y_vec, pdf_y_px, tol_px=tol_px)
        x_lines = _expand_lines_for_points(x_lines, col_x, tol_px)
        y_lines = _expand_lines_for_points(y_lines, col_y, tol_px)

        if column_centers:
            notes.append(f"Column marks (C#): {len(column_centers)} — added missing axis lines.")

        if len(x_lines) < _MIN_LINES_PER_AXIS:
            notes.append("Few vertical lines detected; try a tighter crop or CAD PDF.")
        if len(y_lines) < _MIN_LINES_PER_AXIS:
            notes.append("Few horizontal lines detected.")

        x_lines = sorted(set(x_lines))[:_MAX_LINES_PER_AXIS]
        y_lines = sorted(set(y_lines))[:_MAX_LINES_PER_AXIS]

        if len(x_lines) < 2 or len(y_lines) < 2:
            return RegionGridGeometry(
                crop_width_px=crop_w,
                crop_height_px=crop_h,
                notes=notes or ["Insufficient grid lines in PDF vectors."],
                source="none",
            )

        vertices: list[GridVertex] = []
        for iy, y in enumerate(y_lines):
            for ix, x in enumerate(x_lines):
                vertices.append(
                    GridVertex(grid_index_x=ix, grid_index_y=iy, x_px=float(x), y_px=float(y))
                )

        span_w_mm, span_h_mm = _span_from_pdf_text(page, clip)
        mm_per_px = None
        if span_w_mm and crop_w > 0:
            mm_per_px = span_w_mm / crop_w

        notes.append(
            f"Grid from PDF vectors: {len(x_lines)} X × {len(y_lines)} Y "
            f"({len(vertices)} vertices)."
        )

        return RegionGridGeometry(
            crop_width_px=crop_w,
            crop_height_px=crop_h,
            x_lines_px=x_lines,
            y_lines_px=y_lines,
            vertices=vertices,
            mm_per_px=mm_per_px,
            span_width_mm=span_w_mm,
            span_height_mm=span_h_mm,
            source="pdf_vectors",
            notes=notes,
        )
    finally:
        doc.close()


def build_grid_svg(geom: RegionGridGeometry, *, show_vertices: bool = True) -> str:
    w, h = geom.crop_width_px, geom.crop_height_px
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="100%" height="100%" preserveAspectRatio="none">',
        f'<rect width="{w}" height="{h}" fill="none"/>',
        '<g id="grid-lines" stroke-width="1.5" fill="none">',
    ]
    for x in geom.x_lines_px:
        parts.append(
            f'<line x1="{x:.2f}" y1="0" x2="{x:.2f}" y2="{h}" '
            f'stroke="rgba(251,146,60,0.85)"/>'
        )
    for y in geom.y_lines_px:
        parts.append(
            f'<line x1="0" y1="{y:.2f}" x2="{w}" y2="{y:.2f}" '
            f'stroke="rgba(56,189,248,0.85)"/>'
        )
    parts.append("</g>")
    if show_vertices and geom.vertices:
        parts.append('<g id="vertices" fill="none" stroke="rgba(34,197,94,0.5)" stroke-width="1">')
        for v in geom.vertices:
            parts.append(
                f'<circle cx="{v.x_px:.2f}" cy="{v.y_px:.2f}" r="5" '
                f'data-ix="{v.grid_index_x}" data-iy="{v.grid_index_y}"/>'
            )
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def nearest_vertex(
    geom: RegionGridGeometry,
    x_px: float,
    y_px: float,
    *,
    radius_px: float = 18.0,
) -> GridVertex | None:
    best: GridVertex | None = None
    best_d = radius_px * radius_px
    for v in geom.vertices:
        d = (v.x_px - x_px) ** 2 + (v.y_px - y_px) ** 2
        if d <= best_d:
            best_d = d
            best = v
    return best


def geometry_to_response(geom: RegionGridGeometry) -> dict:
    from analyzer_service.region_analysis_schemas import (
        GridVertexDTO,
        RegionGridGeometryResponse,
    )

    ok = len(geom.x_lines_px) >= 2 and len(geom.y_lines_px) >= 2
    resp = RegionGridGeometryResponse(
        crop_width_px=geom.crop_width_px,
        crop_height_px=geom.crop_height_px,
        x_lines_px=geom.x_lines_px,
        y_lines_px=geom.y_lines_px,
        vertices=[
            GridVertexDTO(
                grid_index_x=v.grid_index_x,
                grid_index_y=v.grid_index_y,
                x_px=v.x_px,
                y_px=v.y_px,
            )
            for v in geom.vertices
        ],
        svg_markup=build_grid_svg(geom) if ok else "",
        mm_per_px=geom.mm_per_px,
        span_width_mm=geom.span_width_mm,
        span_height_mm=geom.span_height_mm,
        source=geom.source,
        notes=geom.notes,
        ok=ok,
        error=None if ok else (geom.notes[-1] if geom.notes else "insufficient_grid_lines"),
    )
    return resp.model_dump()


def geometry_from_response(data: "RegionGridGeometryResponse") -> RegionGridGeometry:
    from analyzer_service.region_analysis_schemas import RegionGridGeometryResponse

    if isinstance(data, RegionGridGeometryResponse):
        dto = data
    else:
        dto = RegionGridGeometryResponse.model_validate(data)
    vertices = [
        GridVertex(
            grid_index_x=v.grid_index_x,
            grid_index_y=v.grid_index_y,
            x_px=v.x_px,
            y_px=v.y_px,
        )
        for v in dto.vertices
    ]
    return RegionGridGeometry(
        crop_width_px=dto.crop_width_px,
        crop_height_px=dto.crop_height_px,
        x_lines_px=list(dto.x_lines_px),
        y_lines_px=list(dto.y_lines_px),
        vertices=vertices,
        mm_per_px=dto.mm_per_px,
        span_width_mm=dto.span_width_mm,
        span_height_mm=dto.span_height_mm,
        source=dto.source,
        notes=list(dto.notes),
    )


def intersections_to_analysis(
    geom: RegionGridGeometry,
    intersections: list[ActiveColumnIntersection],
    *,
    column_profile: str = "HEB200",
    height_mm: float = 6000.0,
) -> RegionStructuralAnalysis:
    """Build RegionStructuralAnalysis from editor state for existing compile path."""
    xs_mm: list[float] = []
    ys_mm: list[float] = []
    if geom.mm_per_px and geom.x_lines_px:
        xs_mm = [round(x * geom.mm_per_px, 1) for x in geom.x_lines_px]
    else:
        xs_mm = [float(i) for i in range(len(geom.x_lines_px))]
    if geom.mm_per_px and geom.y_lines_px:
        ys_mm = [round(y * geom.mm_per_px, 1) for y in geom.y_lines_px]
    else:
        ys_mm = [float(i) for i in range(len(geom.y_lines_px))]

    if xs_mm and xs_mm[0] > 1.0:
        origin = xs_mm[0]
        xs_mm = [round(v - origin, 1) for v in xs_mm]
    if ys_mm and ys_mm[0] > 1.0:
        origin = ys_mm[0]
        ys_mm = [round(v - origin, 1) for v in ys_mm]

    x_text = ", ".join(str(int(v) if v == int(v) else v) for v in xs_mm)
    y_text = ", ".join(str(int(v) if v == int(v) else v) for v in ys_mm)

    return RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=xs_mm,
        y_grid_positions_mm=ys_mm,
        active_column_intersections=intersections,
        detected_parameters=[
            DetectedParameterEntry(key="column_profile", value=column_profile),
            DetectedParameterEntry(key="grid_lines_x_mm", value=x_text),
            DetectedParameterEntry(key="grid_lines_y_mm", value=y_text),
            DetectedParameterEntry(key="grid_extraction_source", value="svg_snap_editor"),
            DetectedParameterEntry(key="column_height_mm", value=str(int(height_mm))),
        ],
    )

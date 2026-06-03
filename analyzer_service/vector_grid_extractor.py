"""
Extract structural grid lines from PDF vectors inside a crop (pdfplumber).

Returns sorted PDF point coordinates for vertical (grid_lines_x) and
horizontal (grid_lines_y) lines — used for deterministic snap-to-grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from analyzer_service.pdf_project_storage import project_dir
from analyzer_service.region_analysis_schemas import CropRectNorm
from analyzer_service.region_pdf_grid import _fitz_page_index

# PDF user space: origin top-left, y increases downward (matches pdfplumber & browser crop).
_MIN_LINE_LEN_PT = 40.0
_ORTHO_TOL_PT = 6.0
_CLUSTER_TOL_PT = 8.0
_MAX_LINES_PER_AXIS = 24
_MAX_USABLE_LINES_PER_AXIS = 20
_EDGE_MARGIN_FRAC = 0.04
_EDGE_CLUSTER_FRAC = 0.45
_MIN_SPAN_FRAC = 0.22
_MIN_SPACING_FRAC = 0.03


@dataclass
class CropBoundsPt:
    """Crop rectangle in PDF points (top-left origin)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)


@dataclass
class VectorGridExtraction:
    grid_lines_x: list[float] = field(default_factory=list)
    grid_lines_y: list[float] = field(default_factory=list)
    crop_bounds: CropBoundsPt | None = None
    source: str = "pdfplumber"
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UserPin:
    """Column mark in crop-normalized coords and/or PDF points."""

    id: str
    x_norm: float = 0.0
    y_norm: float = 0.0
    x_pt: float | None = None
    y_pt: float | None = None
    mark: str | None = None


@dataclass
class AlignedColumnPin:
    id: str
    x_norm: float
    y_norm: float
    x_pt: float
    y_pt: float
    snapped_x_pt: float
    snapped_y_pt: float
    grid_index_x: int
    grid_index_y: int
    mark: str | None = None


def crop_bounds_from_norm(page_width: float, page_height: float, crop: CropRectNorm) -> CropBoundsPt:
    x0 = crop.x * page_width
    y0 = crop.y * page_height
    return CropBoundsPt(
        x0=x0,
        y0=y0,
        x1=x0 + crop.w * page_width,
        y1=y0 + crop.h * page_height,
    )


def norm_to_pdf_point(x_norm: float, y_norm: float, bounds: CropBoundsPt) -> tuple[float, float]:
    """Map 0..1 crop-relative coords → absolute PDF points."""
    x = bounds.x0 + max(0.0, min(1.0, x_norm)) * bounds.width
    y = bounds.y0 + max(0.0, min(1.0, y_norm)) * bounds.height
    return x, y


def pdf_point_to_norm(x_pt: float, y_pt: float, bounds: CropBoundsPt) -> tuple[float, float]:
    if bounds.width <= 0 or bounds.height <= 0:
        return 0.0, 0.0
    return (
        (x_pt - bounds.x0) / bounds.width,
        (y_pt - bounds.y0) / bounds.height,
    )


def assess_vector_grid_quality(
    grid_lines_x: list[float],
    grid_lines_y: list[float],
    bounds: CropBoundsPt,
) -> tuple[bool, list[str]]:
    """
    Reject noisy pdfplumber output (page borders, symbol hatching, title blocks).
    """
    reasons: list[str] = []
    if len(grid_lines_x) < 2 or len(grid_lines_y) < 2:
        return False, ["too_few_lines"]
    if len(grid_lines_x) > _MAX_USABLE_LINES_PER_AXIS or len(grid_lines_y) > _MAX_USABLE_LINES_PER_AXIS:
        return False, [f"too_many_lines_x={len(grid_lines_x)}_y={len(grid_lines_y)}"]

    w, h = bounds.width, bounds.height
    if w <= 0 or h <= 0:
        return False, ["invalid_crop_bounds"]

    mx = w * _EDGE_MARGIN_FRAC
    my = h * _EDGE_MARGIN_FRAC
    edge_x = sum(
        1
        for x in grid_lines_x
        if x <= bounds.x0 + mx or x >= bounds.x1 - mx
    )
    edge_y = sum(
        1
        for y in grid_lines_y
        if y <= bounds.y0 + my or y >= bounds.y1 - my
    )
    if edge_x / len(grid_lines_x) > _EDGE_CLUSTER_FRAC:
        reasons.append("x_lines_on_crop_edges")
    if edge_y / len(grid_lines_y) > _EDGE_CLUSTER_FRAC:
        reasons.append("y_lines_on_crop_edges")

    def _min_spacing(stations: list[float], span: float) -> float:
        if len(stations) < 2:
            return span
        return min(stations[i + 1] - stations[i] for i in range(len(stations) - 1))

    min_gap_x = _min_spacing(sorted(grid_lines_x), w)
    min_gap_y = _min_spacing(sorted(grid_lines_y), h)
    if min_gap_x < w * _MIN_SPACING_FRAC:
        reasons.append("x_lines_too_dense")
    if min_gap_y < h * _MIN_SPACING_FRAC:
        reasons.append("y_lines_too_dense")

    return (len(reasons) == 0, reasons)


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


def _line_intersects_crop(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    crop: CropBoundsPt,
) -> bool:
    left = max(min(x0, x1), crop.x0)
    right = min(max(x0, x1), crop.x1)
    top = max(min(y0, y1), crop.y0)
    bottom = min(max(y0, y1), crop.y1)
    return right >= left and bottom >= top


def _extract_lines_from_page(page, crop: CropBoundsPt) -> tuple[list[float], list[float]]:
    """Long orthogonal segments only — skip rectangle/hatch edges."""
    xs: list[float] = []
    ys: list[float] = []
    min_len = max(_MIN_LINE_LEN_PT, _MIN_SPAN_FRAC * min(crop.width, crop.height))

    for line in page.lines or []:
        x0, y0 = float(line["x0"]), float(line["top"])
        x1, y1 = float(line["x1"]), float(line["bottom"])
        if not _line_intersects_crop(x0, y0, x1, y1, crop):
            continue
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if length < min_len:
            continue
        if abs(x1 - x0) <= _ORTHO_TOL_PT and abs(y1 - y0) >= _MIN_SPAN_FRAC * crop.height:
            xs.append((x0 + x1) / 2.0)
        elif abs(y1 - y0) <= _ORTHO_TOL_PT and abs(x1 - x0) >= _MIN_SPAN_FRAC * crop.width:
            ys.append((y0 + y1) / 2.0)

    cluster_tol = max(_CLUSTER_TOL_PT, min(crop.width, crop.height) * 0.008)
    return (
        _cluster_coords(xs, cluster_tol)[:_MAX_LINES_PER_AXIS],
        _cluster_coords(ys, cluster_tol)[:_MAX_LINES_PER_AXIS],
    )


def extract_vector_grid_from_pdf(
    pdf_path: str | Path,
    page_index: int,
    crop: CropRectNorm,
) -> VectorGridExtraction:
    """Extract vertical/horizontal grid lines in PDF points inside crop."""
    import pdfplumber

    path = Path(pdf_path)
    notes: list[str] = []
    idx = _fitz_page_index(page_index)

    with pdfplumber.open(path) as doc:
        if idx >= len(doc.pages):
            return VectorGridExtraction(notes=[f"Page index {page_index} out of range"])
        page = doc.pages[idx]
        bounds = crop_bounds_from_norm(float(page.width), float(page.height), crop)
        cropped = page.within_bbox((bounds.x0, bounds.y0, bounds.x1, bounds.y1))
        x_lines, y_lines = _extract_lines_from_page(cropped, bounds)

    usable, quality_notes = assess_vector_grid_quality(x_lines, y_lines, bounds)
    if not usable:
        notes.extend(quality_notes)
        notes.append(
            f"pdfplumber rejected ({len(x_lines)} X × {len(y_lines)} Y) — use dimension bays / exact clicks."
        )
        return VectorGridExtraction(
            grid_lines_x=[],
            grid_lines_y=[],
            crop_bounds=bounds,
            source="none",
            notes=notes,
        )

    notes.append(
        f"pdfplumber structural grid: {len(x_lines)} X × {len(y_lines)} Y lines."
    )

    return VectorGridExtraction(
        grid_lines_x=sorted(x_lines),
        grid_lines_y=sorted(y_lines),
        crop_bounds=bounds,
        source="pdfplumber_structural",
        notes=notes,
    )


def extract_vector_grid_for_project(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
) -> VectorGridExtraction | None:
    pdf_path = project_dir(project_id) / "source.pdf"
    if not pdf_path.is_file():
        return None
    return extract_vector_grid_from_pdf(pdf_path, page_index, crop)


def _nearest_value(value: float, stations: list[float]) -> tuple[float, int]:
    if not stations:
        return value, 0
    best_i = min(range(len(stations)), key=lambda i: abs(stations[i] - value))
    return stations[best_i], best_i


def align_columns_to_vector_grid(
    user_pins: list[UserPin],
    grid_lines_x: list[float],
    grid_lines_y: list[float],
    *,
    crop_bounds: CropBoundsPt | None = None,
) -> list[AlignedColumnPin]:
    """
    Snap each pin to the closest vector grid line on X and Y (minimum distance in PDF pt).
    """
    if len(grid_lines_x) < 1 or len(grid_lines_y) < 1:
        raise ValueError("grid_lines_x and grid_lines_y must each have at least one line")

    aligned: list[AlignedColumnPin] = []
    for i, pin in enumerate(user_pins):
        if pin.x_pt is not None and pin.y_pt is not None:
            x_pt, y_pt = float(pin.x_pt), float(pin.y_pt)
        elif crop_bounds is not None:
            x_pt, y_pt = norm_to_pdf_point(pin.x_norm, pin.y_norm, crop_bounds)
        else:
            raise ValueError("Pin must have x_pt/y_pt or crop_bounds for norm conversion")

        snapped_x, ix = _nearest_value(x_pt, grid_lines_x)
        snapped_y, iy = _nearest_value(y_pt, grid_lines_y)
        if crop_bounds:
            x_norm, y_norm = pdf_point_to_norm(snapped_x, snapped_y, crop_bounds)
        else:
            x_norm, y_norm = pin.x_norm, pin.y_norm

        aligned.append(
            AlignedColumnPin(
                id=pin.id,
                x_norm=x_norm,
                y_norm=y_norm,
                x_pt=x_pt,
                y_pt=y_pt,
                snapped_x_pt=snapped_x,
                snapped_y_pt=snapped_y,
                grid_index_x=ix,
                grid_index_y=iy,
                mark=pin.mark or f"C{i + 1}",
            )
        )
    return aligned

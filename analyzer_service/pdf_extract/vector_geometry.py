"""Extract structural-looking line segments from CAD vector paths in PDF plans."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

import fitz

from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec

DEFAULT_PROFILE = "IPE200"
POINTS_TO_MM = 25.4 / 72.0
ORTHO_TOL_DEG = 2.0


@dataclass(frozen=True)
class _Segment2D:
    x1: float
    y1: float
    x2: float
    y2: float
    page_index: int
    stroke_width: float = 0.0

    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def midpoint(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    def is_orthogonal(self) -> bool:
        length = self.length()
        if length <= 1e-9:
            return False
        dx = abs(self.x2 - self.x1) / length
        dy = abs(self.y2 - self.y1) / length
        min_ortho = math.cos(math.radians(90 - ORTHO_TOL_DEG))
        return dx >= min_ortho or dy >= min_ortho

    def key(self, grid_mm: float) -> tuple:
        def q(v: float) -> float:
            return round(v / grid_mm) * grid_mm

        a = (q(self.x1), q(self.y1), q(self.x2), q(self.y2))
        b = (a[2], a[3], a[0], a[1])
        return a if a <= b else b


def count_pdf_line_items(data: bytes) -> int:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return sum(_count_page_line_items(page) for page in doc)
    finally:
        doc.close()


def _count_page_line_items(page: fitz.Page) -> int:
    total = 0
    try:
        for path in page.get_drawings():
            total += _line_items_in_path(path)
    except Exception:
        pass
    return total


def _line_items_in_path(path: dict) -> int:
    count = 0
    for item in path.get("items", ()):
        if not item:
            continue
        kind = item[0]
        if kind == "l":
            count += 1
        elif kind in ("re", "qu"):
            count += 4
    return count


def _point_xy(point: object) -> tuple[float, float]:
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return float(point[0]), float(point[1])
    raise TypeError(f"unsupported point type: {type(point)!r}")


def _rect_edges(rect: object) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    if hasattr(rect, "x0"):
        x0, y0, x1, y1 = float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)
    else:
        x0, y0, x1, y1 = (float(v) for v in rect)  # type: ignore[misc]
    return [
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    ]


def _quad_edges(quad: object) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    if hasattr(quad, "ul"):
        pts = [quad.ul, quad.ur, quad.lr, quad.ll]
    else:
        pts = list(quad)  # type: ignore[arg-type]
    return [
        (_point_xy(pts[i]), _point_xy(pts[(i + 1) % 4]))
        for i in range(4)
    ]


def _segments_from_path(path: dict, page_index: int) -> list[_Segment2D]:
    width = float(path.get("width") or 0.0)
    segments: list[_Segment2D] = []
    for item in path.get("items", ()):
        if not item:
            continue
        kind = item[0]
        try:
            if kind == "l":
                p1, p2 = _point_xy(item[1]), _point_xy(item[2])
                segments.append(_Segment2D(p1[0], p1[1], p2[0], p2[1], page_index, width))
            elif kind == "re":
                for (a, b) in _rect_edges(item[1]):
                    segments.append(_Segment2D(a[0], a[1], b[0], b[1], page_index, width))
            elif kind == "qu":
                for (a, b) in _quad_edges(item[1]):
                    segments.append(_Segment2D(a[0], a[1], b[0], b[1], page_index, width))
        except (TypeError, IndexError, ValueError):
            continue
    return segments


def _parse_scale_mm_per_unit(scale_note: str | None) -> float | None:
    if not scale_note:
        return None
    text = scale_note.strip().lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*/\s*(?:pdf\s*)?(?:unit|pt|point)", text)
    if m:
        return float(m.group(1))
    if re.search(r"grid\s*(?:spacing\s*)?[=:]?\s*(\d{3,6})", text) or re.search(
        r"units?\s*[=:]?\s*mm", text
    ):
        return 1.0
    return None


def _infer_mm_per_unit(
    coords: list[float],
    segments: list[_Segment2D],
    scale_note: str | None,
) -> float:
    from_note = _parse_scale_mm_per_unit(scale_note)
    if from_note is not None:
        return from_note
    if not coords:
        return POINTS_TO_MM

    lengths = sorted(seg.length() for seg in segments if seg.length() > 1e-6)
    median_len = lengths[len(lengths) // 2] if lengths else 0.0
    if median_len > 12_000:
        return POINTS_TO_MM
    if max(coords) - min(coords) > 4_000 or median_len > 400:
        return 1.0
    if max(coords) - min(coords) < 80:
        return 1000.0
    return POINTS_TO_MM


def _score_plan_page(page: fitz.Page, page_index: int) -> tuple[int, float]:
    """Prefer the sheet that looks like a main structural plan (many long orthogonal lines)."""
    segments: list[_Segment2D] = []
    try:
        for path in page.get_drawings():
            segments.extend(_segments_from_path(path, page_index))
    except Exception:
        return (0, 0.0)

    structural = 0
    total_len = 0.0
    for seg in segments:
        length = seg.length()
        if length < 80:
            continue
        if not seg.is_orthogonal():
            continue
        if length < 150 or length > 25_000:
            continue
        structural += 1
        total_len += length
    return (structural, total_len)


def _select_primary_page_index(doc: fitz.Document) -> int:
    best_index = 0
    best_score = (-1, -1.0)
    for index, page in enumerate(doc):
        score = _score_plan_page(page, index)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def select_primary_plan_page_index(data: bytes) -> int:
    """Pick the sheet that looks most like the main structural floor plan (0-based index)."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return _select_primary_page_index(doc)
    finally:
        doc.close()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def _content_bounds_mm(
    segments: list[_Segment2D],
    *,
    margin_pct: float = 3.0,
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for seg in segments:
        xs.extend((seg.x1, seg.x2))
        ys.extend((seg.y1, seg.y2))
    return (
        _percentile(xs, margin_pct),
        _percentile(ys, margin_pct),
        _percentile(xs, 100 - margin_pct),
        _percentile(ys, 100 - margin_pct),
    )


def _segment_inside_bounds(seg: _Segment2D, bounds: tuple[float, float, float, float]) -> bool:
    min_x, min_y, max_x, max_y = bounds
    mx, my = seg.midpoint()
    return min_x <= mx <= max_x and min_y <= my <= max_y


def _merge_collinear(segments: list[_Segment2D], grid_mm: float) -> list[_Segment2D]:
    """Merge overlapping collinear segments on the same grid line."""
    horiz: dict[tuple[int, list[float]], None] = {}
    vert: dict[tuple[int, list[float]], None] = {}
    merged: list[_Segment2D] = []

    def q(v: float) -> int:
        return int(round(v / grid_mm))

    for seg in segments:
        dx = abs(seg.x2 - seg.x1)
        dy = abs(seg.y2 - seg.y1)
        if dx >= dy:
            yk = q((seg.y1 + seg.y2) / 2.0)
            key = (yk,)
            interval = [min(seg.x1, seg.x2), max(seg.x1, seg.x2)]
            bucket = horiz.setdefault(key, [])
            bucket.extend(interval)
        else:
            xk = q((seg.x1 + seg.x2) / 2.0)
            key = (xk,)
            interval = [min(seg.y1, seg.y2), max(seg.y1, seg.y2)]
            bucket = vert.setdefault(key, [])
            bucket.extend(interval)

    for (yk,), intervals in horiz.items():
        points = sorted(intervals)
        start = points[0]
        end = points[1]
        for i in range(2, len(points), 2):
            s, e = points[i], points[i + 1]
            if s <= end + grid_mm:
                end = max(end, e)
            else:
                if end - start >= grid_mm:
                    y = float(yk * grid_mm)
                    merged.append(_Segment2D(start, y, end, y, segments[0].page_index))
                start, end = s, e
        if end - start >= grid_mm:
            y = float(yk * grid_mm)
            merged.append(_Segment2D(start, y, end, y, segments[0].page_index))

    for (xk,), intervals in vert.items():
        points = sorted(intervals)
        start = points[0]
        end = points[1]
        for i in range(2, len(points), 2):
            s, e = points[i], points[i + 1]
            if s <= end + grid_mm:
                end = max(end, e)
            else:
                if end - start >= grid_mm:
                    x = float(xk * grid_mm)
                    merged.append(_Segment2D(x, start, x, end, segments[0].page_index))
                start, end = s, e
        if end - start >= grid_mm:
            x = float(xk * grid_mm)
            merged.append(_Segment2D(x, start, x, end, segments[0].page_index))

    return merged if merged else segments


@dataclass
class _PageExtractAttempt:
    page_index: int
    mm_per_unit: float
    min_length_mm: float
    require_orthogonal: bool
    raw_count: int
    kept_count: int
    segments: list[_Segment2D]


def _scale_candidates(
    raw_segments: list[_Segment2D],
    all_coords: list[float],
    scale_note: str | None,
) -> list[float]:
    explicit = _parse_scale_mm_per_unit(scale_note)
    inferred = _infer_mm_per_unit(all_coords, raw_segments, scale_note)
    candidates = [explicit, inferred, 1.0, POINTS_TO_MM]
    unique: list[float] = []
    for value in candidates:
        if value is None:
            continue
        if not any(abs(value - existing) < 1e-6 for existing in unique):
            unique.append(value)
    return unique


def _filter_segments_on_page(
    raw_segments: list[_Segment2D],
    *,
    mm_per_unit: float,
    min_length_mm: float,
    min_stroke: float,
    require_orthogonal: bool,
) -> list[_Segment2D]:
    scaled: list[_Segment2D] = []
    for seg in raw_segments:
        length_mm = seg.length() * mm_per_unit
        if length_mm < min_length_mm:
            continue
        if min_stroke > 0 and seg.stroke_width < min_stroke:
            continue
        if require_orthogonal and not seg.is_orthogonal():
            continue
        scaled.append(
            _Segment2D(
                seg.x1 * mm_per_unit,
                seg.y1 * mm_per_unit,
                seg.x2 * mm_per_unit,
                seg.y2 * mm_per_unit,
                seg.page_index,
                seg.stroke_width,
            )
        )
    return scaled


def _structural_stroke_threshold(segments: list[_Segment2D]) -> float:
    """Drop dimension/tick linework — keep strokes typical of grid and members."""
    widths = sorted(seg.stroke_width for seg in segments if seg.stroke_width > 0.05)
    if len(widths) < 30:
        return 0.0
    mid = widths[len(widths) // 2]
    upper = widths[int(len(widths) * 0.72)]
    return max(0.0, min(mid, upper * 0.85))


def _try_extract_page(
    doc: fitz.Document,
    page_index: int,
    *,
    scale_note: str | None,
    min_length_mm: float,
    require_orthogonal: bool,
    min_stroke: float,
) -> _PageExtractAttempt | None:
    page = doc[page_index]
    raw_segments: list[_Segment2D] = []
    all_coords: list[float] = []
    try:
        for path in page.get_drawings():
            raw_segments.extend(_segments_from_path(path, page_index))
    except Exception:
        return None

    if not raw_segments:
        return None

    for seg in raw_segments:
        all_coords.extend((seg.x1, seg.y1, seg.x2, seg.y2))

    auto_stroke = _structural_stroke_threshold(raw_segments)
    stroke_floor = max(min_stroke, auto_stroke) if min_stroke <= 0 else min_stroke

    for mm_per_unit in _scale_candidates(raw_segments, all_coords, scale_note):
        for stroke_use, ortho_use in (
            (stroke_floor, require_orthogonal),
            (max(0.0, stroke_floor * 0.5), require_orthogonal),
            (0.0, require_orthogonal),
            (0.0, False),
        ):
            scaled = _filter_segments_on_page(
                raw_segments,
                mm_per_unit=mm_per_unit,
                min_length_mm=min_length_mm,
                min_stroke=stroke_use,
                require_orthogonal=ortho_use,
            )
            if scaled:
                return _PageExtractAttempt(
                    page_index=page_index,
                    mm_per_unit=mm_per_unit,
                    min_length_mm=min_length_mm,
                    require_orthogonal=ortho_use,
                    raw_count=len(raw_segments),
                    kept_count=len(scaled),
                    segments=scaled,
                )
    return None


def extract_pure_model_from_pdf_vectors(
    data: bytes,
    *,
    scale_note: str | None = None,
    page_index: int | None = None,
) -> tuple[PureStructuralModelSpec, list[str]]:
    """
    Build a 2D plan wireframe from CAD vector lines (no AI).

    Tries multiple sheets and scale guesses before failing.
    """
    min_length_mm = float(os.getenv("PDF_VECTOR_MIN_LENGTH_MM", "600"))
    max_elements = int(os.getenv("PDF_VECTOR_MAX_ELEMENTS", "4000"))
    grid_mm = float(os.getenv("PDF_VECTOR_DEDUP_GRID_MM", "25"))
    min_stroke = float(os.getenv("PDF_VECTOR_MIN_STROKE_WIDTH", "0"))
    default_profile = os.getenv("PDF_VECTOR_DEFAULT_PROFILE", DEFAULT_PROFILE).strip() or DEFAULT_PROFILE

    doc = fitz.open(stream=data, filetype="pdf")
    warnings: list[str] = []
    try:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")

        if page_index is not None and 0 <= page_index < doc.page_count:
            page_order = [page_index]
        else:
            page_order = sorted(
                range(doc.page_count),
                key=lambda i: _score_plan_page(doc[i], i),
                reverse=True,
            )

        attempt: _PageExtractAttempt | None = None
        filter_modes = [
            (min_length_mm, True),
            (max(350.0, min_length_mm * 0.45), True),
            (max(200.0, min_length_mm * 0.25), True),
            (max(150.0, min_length_mm * 0.2), False),
        ]
        for pidx in page_order:
            for min_len, ortho in filter_modes:
                attempt = _try_extract_page(
                    doc,
                    pidx,
                    scale_note=scale_note,
                    min_length_mm=min_len,
                    require_orthogonal=ortho,
                    min_stroke=min_stroke,
                )
                if attempt:
                    break
            if attempt:
                break

        if attempt is None:
            raise ValueError(
                f"No usable structural lines on any of {doc.page_count} sheet(s) "
                f"(min length tried down to ~300 mm). Add scale 'units mm', set Hints to "
                "'page 1' for the main plan, or set PDF_FORCE_VISION=1 to use AI vision instead."
            )

        primary_page = attempt.page_index
        if doc.page_count > 1:
            warnings.append(
                f"Using sheet {primary_page + 1} of {doc.page_count} "
                f"(scale {attempt.mm_per_unit:.4g} mm/unit, "
                f"min line {attempt.min_length_mm:.0f} mm"
                f"{'' if attempt.require_orthogonal else ', diagonals allowed'})."
            )

        scaled = attempt.segments
        bounds = _content_bounds_mm(scaled)
        scaled = [s for s in scaled if _segment_inside_bounds(s, bounds)]
        scaled = _merge_collinear(scaled, grid_mm)

        deduped: dict[tuple, _Segment2D] = {seg.key(grid_mm): seg for seg in scaled}
        segments = list(deduped.values())

        if len(segments) > max_elements:
            segments.sort(key=lambda s: s.length(), reverse=True)
            segments = segments[:max_elements]
            warnings.append(f"Truncated to {max_elements} longest structural lines.")

        min_x = min(min(s.x1, s.x2) for s in segments)
        min_y = min(min(s.y1, s.y2) for s in segments)

        elements: list[PureSteelElementSpec] = []
        for index, seg in enumerate(segments):
            elements.append(
                PureSteelElementSpec(
                    id=f"p{primary_page + 1}_{index + 1}",
                    profile_name=default_profile,
                    start_x=seg.x1 - min_x,
                    start_y=seg.y1 - min_y,
                    start_z=0.0,
                    end_x=seg.x2 - min_x,
                    end_y=seg.y2 - min_y,
                    end_z=0.0,
                )
            )

        warnings.append(
            "CAD vector plan wireframe from PDF linework (real geometry, Z=0 plan level). "
            "Multi-storey heights come from section sheets or future elevation pass."
        )
        warnings.append(
            f"Structural lines kept: {len(elements)} (from {attempt.raw_count} raw vectors on sheet "
            f"{primary_page + 1})."
        )
        return PureStructuralModelSpec(elements=elements, slabs=None), warnings
    finally:
        doc.close()

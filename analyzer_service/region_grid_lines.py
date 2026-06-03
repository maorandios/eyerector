"""
Detect structural grid lines in a crop: axis labels (1,2,3 / A,B,C) + long PDF vectors.

Never merge dimension-chain pseudo-positions into vector px (that shifts the grid).
"""

from __future__ import annotations

import re

import fitz

from analyzer_service.pdf_extract.vector_geometry import _infer_mm_per_unit, _segments_from_path
from analyzer_service.region_pdf_grid import (
    PdfGridExtraction,
    _clip_rect,
    _fitz_page_index,
    _text_spans_in_clip,
)
from analyzer_service.region_grid_geometry import (
    _cluster_coords,
    _cluster_weighted,
    _pt_to_crop_px,
    _seg_intersects_clip,
)

_GRID_NUM_RE = re.compile(r"^\d{1,2}$")
_GRID_LETTER_RE = re.compile(r"^[A-Z]$")


def _extract_long_vectors_px(
    page: fitz.Page,
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
) -> tuple[list[float], list[float]]:
    """Long orthogonal segments only (major grid, not ticks)."""
    tol_px = max(8.0, min(crop_w, crop_h) * 0.003)
    min_long_v = max(40.0, crop_h * 0.22)
    min_long_h = max(40.0, crop_w * 0.22)

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
                if dx <= 8.0 and length >= min_long_v:
                    for x_pt in (seg.x1, seg.x2):
                        if clip.x0 <= x_pt <= clip.x1:
                            x_px, _ = _pt_to_crop_px(x_pt, clip.y0, clip, crop_w, crop_h)
                            x_samples.append((x_px, length))
                elif dy <= 8.0 and length >= min_long_h:
                    for y_pt in (seg.y1, seg.y2):
                        if clip.y0 <= y_pt <= clip.y1:
                            _, y_px = _pt_to_crop_px(clip.x0, y_pt, clip, crop_w, crop_h)
                            y_samples.append((y_px, length))
    except Exception:
        pass

    return (
        _cluster_weighted(x_samples, tol_px),
        _cluster_weighted(y_samples, tol_px),
    )


def _axis_label_grid_px(
    page: fitz.Page,
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
) -> tuple[list[float], list[float]]:
    """Grid line px at axis bubble labels (1…13, A…C)."""
    band_y = 0.14 * clip.height
    band_x = 0.14 * clip.width
    x_by_num: dict[int, list[float]] = {}
    y_by_letter: dict[str, list[float]] = {}

    for x0, y0, x1, y1, text in _text_spans_in_clip(page, clip):
        raw = text.strip().upper()
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        x_px, y_px = _pt_to_crop_px(cx, cy, clip, crop_w, crop_h)

        num_m = _GRID_NUM_RE.match(raw)
        if num_m and (cy <= clip.y0 + band_y or cy >= clip.y1 - band_y):
            n = int(raw)
            x_by_num.setdefault(n, []).append(x_px)

        let_m = _GRID_LETTER_RE.match(raw)
        if let_m and cx <= clip.x0 + band_x:
            y_by_letter.setdefault(raw, []).append(y_px)

    x_lines = [
        sum(x_by_num[k]) / len(x_by_num[k]) for k in sorted(x_by_num.keys())
    ]
    y_lines = [
        sum(y_by_letter[k]) / len(y_by_letter[k])
        for k in sorted(y_by_letter.keys())
    ]
    return x_lines, y_lines


def _clip_lines_to_label_span(
    lines: list[float],
    label_positions: list[float],
    crop_span: float,
    *,
    margin_frac: float = 0.03,
) -> list[float]:
    """Drop border/title-block vectors outside the numbered/lettered grid span."""
    if len(label_positions) < 2 or not lines:
        return lines
    margin = max(12.0, crop_span * margin_frac)
    lo = min(label_positions) - margin
    hi = max(label_positions) + margin
    clipped = [v for v in lines if lo <= v <= hi]
    return clipped if len(clipped) >= 2 else lines


def _snap_labels_to_vectors(
    label_lines: list[float],
    vec_lines: list[float],
    crop_span: float,
    *,
    max_lines: int = 20,
) -> list[float]:
    """One line per axis bubble; snap to nearest real PDF segment (not label text x)."""
    if len(label_lines) < 2:
        if len(vec_lines) >= 2:
            return _thin_lines(vec_lines, crop_span, max_lines=max_lines)
        return []
    tol = max(18.0, crop_span * 0.018)
    search = tol * 3.0
    vec_sorted = sorted(vec_lines)
    fused: list[float] = []
    used: set[float] = set()
    for lbl in sorted(label_lines):
        candidates = [v for v in vec_sorted if abs(v - lbl) <= search and v not in used]
        if candidates:
            pick = min(candidates, key=lambda v: abs(v - lbl))
            fused.append(pick)
            used.add(pick)
        else:
            fused.append(lbl)
    out = _dedupe_lines(sorted(fused), min_gap=tol * 0.6)
    return out[:max_lines]


def _fuse_label_vector(
    label_lines: list[float],
    vec_lines: list[float],
    crop_span: float,
    *,
    max_lines: int = 20,
) -> list[float]:
    return _snap_labels_to_vectors(
        label_lines, vec_lines, crop_span, max_lines=max_lines
    )


def _dedupe_lines(lines: list[float], min_gap: float = 1.0) -> list[float]:
    if not lines:
        return []
    out: list[float] = []
    for v in sorted(lines):
        if not out or v - out[-1] >= min_gap:
            out.append(v)
    return out


def _cluster_click_axis_px(values: list[float], crop_span: float) -> list[float]:
    if not values:
        return []
    tol = max(14.0, crop_span * 0.022)
    return _dedupe_lines(_cluster_coords(values, tol), min_gap=tol * 0.5)


def _thin_lines(lines: list[float], crop_span: float, *, max_lines: int = 20) -> list[float]:
    if not lines:
        return []
    clustered = sorted(set(_cluster_coords(lines, max(10.0, crop_span * 0.025))))
    if len(clustered) <= max_lines:
        return clustered
    min_gap = max(14.0, crop_span * 0.04)
    out = [clustered[0]]
    for v in clustered[1:]:
        if v - out[-1] >= min_gap:
            out.append(v)
        if len(out) >= max_lines:
            break
    if clustered[-1] - out[-1] >= min_gap:
        out.append(clustered[-1])
    return out


def _mm_stations_x(lines_px: list[float], mm_per_px: float) -> list[float]:
    """Absolute mm from crop left (X)."""
    return [round(x * mm_per_px, 1) for x in sorted(lines_px)]


def _mm_stations_y(lines_px: list[float], crop_h: int, mm_per_px: float) -> list[float]:
    """Absolute mm from crop bottom (Y up) — matches snap query span_y - y_px*mm."""
    return [round((crop_h - y) * mm_per_px, 1) for y in sorted(lines_px)]


def build_crop_grid(
    page: fitz.Page,
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
    pdf_grid: PdfGridExtraction | None,
    *,
    scale_note: str | None = None,
    click_x_px: list[float] | None = None,
    click_y_px: list[float] | None = None,
) -> tuple[list[float], list[float], list[float], list[float], float, float, list[str]]:
    """
    Returns x_lines_px, y_lines_px, xs_mm, ys_mm, mm_x, mm_y, notes.
    """
    notes: list[str] = []
    segments: list = []
    for path in page.get_drawings():
        segments.extend(_segments_from_path(path, 0))
    mm_per_pt = _infer_mm_per_unit(
        [clip.x0, clip.x1, clip.y0, clip.y1], segments, scale_note
    )
    mm_x = (clip.width * mm_per_pt) / crop_w if crop_w > 0 else mm_per_pt
    mm_y = (clip.height * mm_per_pt) / crop_h if crop_h > 0 else mm_x

    x_vec, y_vec = _extract_long_vectors_px(page, clip, crop_w, crop_h)
    x_lbl, y_lbl = _axis_label_grid_px(page, clip, crop_w, crop_h)

    if len(x_lbl) >= 2:
        notes.append(f"Grid X from axis labels ({len(x_lbl)} lines).")
    if len(y_lbl) >= 2:
        notes.append(f"Grid Y from axis labels ({len(y_lbl)} lines).")

    if len(x_lbl) >= 2:
        x_lines = _snap_labels_to_vectors(x_lbl, x_vec, crop_w, max_lines=18)
        x_lines = _clip_lines_to_label_span(x_lines, x_lbl, crop_w)
        notes.append(f"Grid X: {len(x_lbl)} axis labels → {len(x_lines)} vector lines.")
    else:
        x_lines = _thin_lines(x_vec, crop_w, max_lines=18)
        notes.append(f"Grid X from vectors ({len(x_lines)} lines).")

    if len(y_lbl) >= 2:
        y_lines = _snap_labels_to_vectors(y_lbl, y_vec, crop_h, max_lines=8)
        y_lines = _clip_lines_to_label_span(y_lines, y_lbl, crop_h)
        notes.append(f"Grid Y: {len(y_lbl)} axis labels → {len(y_lines)} vector lines.")
    else:
        y_lines = _thin_lines(y_vec, crop_h, max_lines=8)
        notes.append(f"Grid Y from vectors ({len(y_lines)} lines).")

    tol = max(12.0, min(crop_w, crop_h) * 0.018)
    if click_x_px and len(x_lines) >= 2:
        x_click = _cluster_click_axis_px(list(click_x_px), crop_w)
        if x_click:
            x_lines = _dedupe_lines(
                sorted(_cluster_coords([*x_lines, *x_click], tol)),
                min_gap=tol,
            )[:18]
            notes.append(f"Grid X includes {len(x_click)} click axes.")
    if click_y_px and len(y_lines) >= 2:
        y_click = _cluster_click_axis_px(list(click_y_px), crop_h)
        if y_click:
            y_lines = _dedupe_lines(
                sorted(_cluster_coords([*y_lines, *y_click], tol)),
                min_gap=tol,
            )[:8]
            notes.append(f"Grid Y includes {len(y_click)} click axes.")

    x_lines = _dedupe_lines(sorted(x_lines), min_gap=max(8.0, tol * 0.5))
    y_lines = _dedupe_lines(sorted(y_lines), min_gap=max(8.0, tol * 0.5))
    xs_mm = _mm_stations_x(x_lines, mm_x)
    ys_mm = _mm_stations_y(y_lines, crop_h, mm_y)

    return x_lines, y_lines, xs_mm, ys_mm, mm_x, mm_y, notes

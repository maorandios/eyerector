"""
Canonical grid + column model for plan-crop (extract → edit → finish).

Single source of truth: axis lines in px, stations in mm, columns at intersections.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

import fitz

from analyzer_service.region_analysis_schemas import (
    ColumnPlacement,
    CropRectNorm,
    DetectedParameterEntry,
    RegionStructuralAnalysis,
)
from analyzer_service.region_column_clicks import (
    _detect_column_profile_from_page,
    _load_pdf_grid,
)
from analyzer_service.region_grid_geometry import _crop_pixel_size
from analyzer_service.region_grid_lines import build_crop_grid
from analyzer_service.region_layout_compiler import _normalize_axis_positions
from analyzer_service.region_pdf_grid import _clip_rect, _fitz_page_index, _text_spans_in_clip
from analyzer_service.region_grid_geometry import _pt_to_crop_px
from analyzer_service.pdf_project_storage import project_dir

_COL_MARK_RE = re.compile(r"^C(\d+)$", re.I)
_MIN_LINES = 2
_CLUSTER_TOL_FRAC = 0.022


@dataclass
class GridAxisModel:
    lines_px: list[float] = field(default_factory=list)
    stations_mm: list[float] = field(default_factory=list)
    bays_mm: list[float] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass
class GridColumnModel:
    id: str
    mark: str
    x_px: float
    y_px: float
    x_mm: float
    y_mm: float
    grid_ix: int
    grid_iy: int
    source: str = "detected"
    confidence: float = 0.5


@dataclass
class GridModel:
    crop_width_px: int
    crop_height_px: int
    mm_per_px_x: float
    mm_per_px_y: float
    span_width_mm: float
    span_height_mm: float
    axis_x: GridAxisModel
    axis_y: GridAxisModel
    columns: list[GridColumnModel] = field(default_factory=list)
    suggested_column_profile: str | None = None
    notes: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "crop_width_px": self.crop_width_px,
            "crop_height_px": self.crop_height_px,
            "mm_per_px_x": self.mm_per_px_x,
            "mm_per_px_y": self.mm_per_px_y,
            "span_width_mm": self.span_width_mm,
            "span_height_mm": self.span_height_mm,
            "axis_x": {
                "lines_px": self.axis_x.lines_px,
                "stations_mm": self.axis_x.stations_mm,
                "bays_mm": self.axis_x.bays_mm,
                "labels": self.axis_x.labels,
            },
            "axis_y": {
                "lines_px": self.axis_y.lines_px,
                "stations_mm": self.axis_y.stations_mm,
                "bays_mm": self.axis_y.bays_mm,
                "labels": self.axis_y.labels,
            },
            "columns": [
                {
                    "id": c.id,
                    "mark": c.mark,
                    "x_px": c.x_px,
                    "y_px": c.y_px,
                    "x_mm": c.x_mm,
                    "y_mm": c.y_mm,
                    "grid_ix": c.grid_ix,
                    "grid_iy": c.grid_iy,
                    "source": c.source,
                    "confidence": c.confidence,
                }
                for c in self.columns
            ],
            "suggested_column_profile": self.suggested_column_profile,
            "notes": self.notes,
            "provenance": self.provenance,
        }


def _bays_from_stations(stations: list[float]) -> list[float]:
    if len(stations) < 2:
        return []
    return [round(stations[i + 1] - stations[i], 1) for i in range(len(stations) - 1)]


def _stations_from_bays(bays: list[float]) -> list[float]:
    if not bays:
        return [0.0]
    out = [0.0]
    for b in bays:
        out.append(round(out[-1] + float(b), 1))
    return out


def _dedupe_lines(lines: list[float], min_gap: float) -> list[float]:
    if not lines:
        return []
    out: list[float] = []
    for v in sorted(lines):
        if not out or v - out[-1] >= min_gap:
            out.append(v)
    return out


def _nearest_index(value: float, stations: list[float]) -> int:
    return min(range(len(stations)), key=lambda i: abs(stations[i] - value))


def _lines_px_from_stations(
    stations_mm: list[float],
    span_mm: float,
    crop_span_px: int,
    *,
    vertical: bool,
    crop_h: int,
) -> list[float]:
    if not stations_mm or span_mm <= 0:
        return []
    if vertical:
        return [round((s / span_mm) * crop_span_px, 2) for s in stations_mm]
    return [round(crop_h - (s / span_mm) * crop_h, 2) for s in stations_mm]


def _mm_at_line_px(
    line_px: float,
    stations_mm: list[float],
    lines_px: list[float],
    mm_per_px: float,
    *,
    vertical: bool,
    crop_h: int,
) -> float:
    if not lines_px:
        return round(line_px * mm_per_px, 1) if vertical else round((crop_h - line_px) * mm_per_px, 1)
    ix = _nearest_index(line_px, lines_px)
    if ix < len(stations_mm):
        return stations_mm[ix]
    return round(line_px * mm_per_px, 1) if vertical else round((crop_h - line_px) * mm_per_px, 1)


def _sync_axis(
    lines_px: list[float],
    stations_mm: list[float],
    span_mm: float,
    crop_span_px: int,
    *,
    vertical: bool,
    crop_h: int,
    mm_per_px: float,
) -> tuple[list[float], list[float], list[float]]:
    """
    PDF vector lines (px) are authoritative for overlay.
    mm stations come from line positions — never stretch dimension chains across crop.
    """
    ln = _dedupe_lines(list(lines_px), max(8.0, crop_span_px * 0.01))
    if len(ln) < _MIN_LINES:
        st = _normalize_axis_positions(list(stations_mm))
        return ln, st, _bays_from_stations(st)
    if vertical:
        st = [round(x * mm_per_px, 1) for x in ln]
    else:
        st = [round((crop_h - y) * mm_per_px, 1) for y in ln]
    st = _normalize_axis_positions(st)
    return ln, st, _bays_from_stations(st)


def _axis_labels_numeric(n: int) -> list[str]:
    return [str(i + 1) for i in range(n)]


def _axis_labels_letters(n: int) -> list[str]:
    return [chr(65 + i) for i in range(min(n, 26))]


def _detect_columns_from_text(
    page: fitz.Page,
    clip: fitz.Rect,
    crop_w: int,
    crop_h: int,
    x_lines: list[float],
    y_lines: list[float],
    xs_mm: list[float],
    ys_mm: list[float],
    mm_x: float,
    mm_y: float,
) -> list[GridColumnModel]:
    if len(x_lines) < _MIN_LINES or len(y_lines) < _MIN_LINES:
        return []

    tol = max(28.0, min(crop_w, crop_h) * 0.035)
    cols: list[GridColumnModel] = []
    seen_cells: set[tuple[int, int]] = set()

    for x0, y0, x1, y1, text in _text_spans_in_clip(page, clip):
        raw = text.strip().upper().replace(" ", "")
        m = _COL_MARK_RE.match(raw)
        if not m:
            continue
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        x_px, y_px = _pt_to_crop_px(cx, cy, clip, crop_w, crop_h)
        ix = _nearest_index(x_px, x_lines)
        iy = _nearest_index(y_px, y_lines)
        snap_x = x_lines[min(ix, len(x_lines) - 1)]
        snap_y = y_lines[min(iy, len(y_lines) - 1)]
        if abs(x_px - snap_x) > tol or abs(y_px - snap_y) > tol:
            continue
        if (ix, iy) in seen_cells:
            continue
        seen_cells.add((ix, iy))
        x_mm = xs_mm[min(ix, len(xs_mm) - 1)] if xs_mm else round(snap_x * mm_x, 1)
        y_mm = ys_mm[min(iy, len(ys_mm) - 1)] if ys_mm else round((crop_h - snap_y) * mm_y, 1)
        cols.append(
            GridColumnModel(
                id=str(uuid.uuid4()),
                mark=raw if raw.startswith("C") else f"C{m.group(1)}",
                x_px=snap_x,
                y_px=snap_y,
                x_mm=x_mm,
                y_mm=y_mm,
                grid_ix=ix,
                grid_iy=iy,
                source="detected",
                confidence=0.85,
            )
        )
    return cols


def extract_grid_model(
    project_id: str,
    page_index: int,
    crop: CropRectNorm,
    *,
    scale_note: str | None = None,
) -> GridModel:
    # Match browser crop PNG pixels (manifest), not raw fitz pixmap extent.
    crop_w, crop_h = _crop_pixel_size(project_id, page_index, crop)
    notes: list[str] = []
    provenance: dict[str, str] = {}

    pdf_path = project_dir(project_id) / "source.pdf"
    if not pdf_path.is_file():
        raise FileNotFoundError("source.pdf missing for project")

    pdf_grid = _load_pdf_grid(project_id, page_index, crop, scale_note=scale_note)
    pdf_xs = _normalize_axis_positions(list(pdf_grid.x_stations_mm)) if pdf_grid else []
    pdf_ys = _normalize_axis_positions(list(pdf_grid.y_stations_mm)) if pdf_grid else []

    doc = fitz.open(pdf_path)
    try:
        page = doc[_fitz_page_index(page_index)]
        clip = _clip_rect(page, crop)
        suggested = _detect_column_profile_from_page(page, clip)

        x_lines, y_lines, xs_out, ys_out, mm_x, mm_y, grid_notes = build_crop_grid(
            page,
            clip,
            crop_w,
            crop_h,
            pdf_grid,
            scale_note=scale_note,
        )
        notes.extend(grid_notes)

        mm_x = mm_x or (pdf_xs[-1] / crop_w if pdf_xs and crop_w else 1.0)
        mm_y = mm_y or (pdf_ys[-1] / crop_h if pdf_ys and crop_h else mm_x)

        span_hint_x = xs_out[-1] if xs_out else 1.0
        span_hint_y = ys_out[-1] if ys_out else 1.0
        x_lines, xs_mm, bays_x = _sync_axis(
            x_lines,
            [],
            span_hint_x,
            crop_w,
            vertical=True,
            crop_h=crop_h,
            mm_per_px=mm_x,
        )
        y_lines, ys_mm, bays_y = _sync_axis(
            y_lines,
            [],
            span_hint_y,
            crop_h,
            vertical=False,
            crop_h=crop_h,
            mm_per_px=mm_y,
        )
        span_x = xs_mm[-1] if xs_mm else 1.0
        span_y = ys_mm[-1] if ys_mm else 1.0

        provenance["lines"] = "axis_labels_snapped_to_pdf_vectors"
        provenance["dims"] = "mm_from_line_px_in_crop"
        notes.append(
            f"Overlay: {len(x_lines)} vertical × {len(y_lines)} horizontal (vector px)."
        )
        if pdf_xs:
            notes.append(
                f"PDF dimension chain has {len(pdf_xs)} X bays (mm for 3D, not overlay)."
            )
        if pdf_ys:
            notes.append(f"PDF dimension chain has {len(pdf_ys)} Y bays.")

        columns = _detect_columns_from_text(
            page, clip, crop_w, crop_h, x_lines, y_lines, xs_mm, ys_mm, mm_x, mm_y
        )
        if columns:
            notes.append(f"Detected {len(columns)} column labels (C#) on plan.")
        else:
            notes.append("No C# labels found — add columns in the editor.")

        return GridModel(
            crop_width_px=crop_w,
            crop_height_px=crop_h,
            mm_per_px_x=mm_x,
            mm_per_px_y=mm_y,
            span_width_mm=span_x,
            span_height_mm=span_y,
            axis_x=GridAxisModel(
                lines_px=x_lines,
                stations_mm=xs_mm,
                bays_mm=bays_x,
                labels=_axis_labels_numeric(len(x_lines)),
            ),
            axis_y=GridAxisModel(
                lines_px=y_lines,
                stations_mm=ys_mm,
                bays_mm=bays_y,
                labels=_axis_labels_letters(len(y_lines)),
            ),
            columns=columns,
            suggested_column_profile=suggested,
            notes=notes,
            provenance=provenance,
        )
    finally:
        doc.close()


def grid_model_from_payload(data: dict) -> GridModel:
    """Rebuild GridModel from API/frontend JSON (after user edits)."""
    crop_w = int(data["crop_width_px"])
    crop_h = int(data["crop_height_px"])
    mm_x = float(data.get("mm_per_px_x") or data.get("mm_per_px") or 1)
    mm_y = float(data.get("mm_per_px_y") or mm_x)
    span_x = float(data.get("span_width_mm") or 1)
    span_y = float(data.get("span_height_mm") or 1)

    ax = data.get("axis_x") or {}
    ay = data.get("axis_y") or {}
    xs = _normalize_axis_positions([float(v) for v in ax.get("stations_mm") or []])
    ys = _normalize_axis_positions([float(v) for v in ay.get("stations_mm") or []])
    if len(xs) < _MIN_LINES and ax.get("bays_mm"):
        xs = _stations_from_bays([float(v) for v in ax["bays_mm"]])
    if len(ys) < _MIN_LINES and ay.get("bays_mm"):
        ys = _stations_from_bays([float(v) for v in ay["bays_mm"]])
    if xs:
        span_x = max(span_x, xs[-1])
    if ys:
        span_y = max(span_y, ys[-1])

    x_lines = [float(v) for v in ax.get("lines_px") or []]
    y_lines = [float(v) for v in ay.get("lines_px") or []]
    x_lines, xs, bays_x = _sync_axis(
        x_lines, xs, span_x, crop_w, vertical=True, crop_h=crop_h, mm_per_px=mm_x
    )
    y_lines, ys, bays_y = _sync_axis(
        y_lines, ys, span_y, crop_h, vertical=False, crop_h=crop_h, mm_per_px=mm_y
    )

    columns: list[GridColumnModel] = []
    for c in data.get("columns") or []:
        x_px = max(0.0, min(crop_w, float(c["x_px"])))
        y_px = max(0.0, min(crop_h, float(c["y_px"])))
        ix = int(c.get("grid_ix", 0))
        iy = int(c.get("grid_iy", 0))
        if x_lines and y_lines:
            ix = _nearest_index(x_px, x_lines)
            iy = _nearest_index(y_px, y_lines)
            x_px = x_lines[min(ix, len(x_lines) - 1)]
            y_px = y_lines[min(iy, len(y_lines) - 1)]
        x_mm = xs[min(ix, len(xs) - 1)] if xs else float(c.get("x_mm", 0))
        y_mm = ys[min(iy, len(ys) - 1)] if ys else float(c.get("y_mm", 0))
        columns.append(
            GridColumnModel(
                id=str(c.get("id") or uuid.uuid4()),
                mark=str(c.get("mark") or "C1"),
                x_px=x_px,
                y_px=y_px,
                x_mm=x_mm,
                y_mm=y_mm,
                grid_ix=ix,
                grid_iy=iy,
                source=str(c.get("source") or "user"),
                confidence=float(c.get("confidence") or 1.0),
            )
        )

    return GridModel(
        crop_width_px=crop_w,
        crop_height_px=crop_h,
        mm_per_px_x=mm_x,
        mm_per_px_y=mm_y,
        span_width_mm=span_x,
        span_height_mm=span_y,
        axis_x=GridAxisModel(
            lines_px=x_lines,
            stations_mm=xs,
            bays_mm=bays_x,
            labels=list(ax.get("labels") or _axis_labels_numeric(len(x_lines))),
        ),
        axis_y=GridAxisModel(
            lines_px=y_lines,
            stations_mm=ys,
            bays_mm=bays_y,
            labels=list(ay.get("labels") or _axis_labels_letters(len(y_lines))),
        ),
        columns=columns,
        suggested_column_profile=data.get("suggested_column_profile"),
        notes=list(data.get("notes") or []),
        provenance=dict(data.get("provenance") or {}),
    )


def analysis_from_grid_model(
    model: GridModel,
    *,
    column_profile: str = "HEB200",
    height_mm: float = 6000.0,
) -> RegionStructuralAnalysis:
    if len(model.axis_x.stations_mm) < _MIN_LINES or len(model.axis_y.stations_mm) < _MIN_LINES:
        raise ValueError("Grid needs at least 2 X and 2 Y stations.")

    placements: list[ColumnPlacement] = []
    for i, col in enumerate(model.columns):
        placements.append(
            ColumnPlacement(
                id=f"col_{col.grid_ix}_{col.grid_iy}_{i}",
                x_mm=round(col.x_mm, 1),
                y_mm=round(col.y_mm, 1),
                profile_name=column_profile,
                height_mm=height_mm,
                mark=col.mark,
            )
        )

    if not placements:
        raise ValueError("Add at least one column on the grid before continuing.")

    xs = model.axis_x.stations_mm
    ys = model.axis_y.stations_mm
    x_text = ", ".join(str(int(v) if v == int(v) else v) for v in xs)
    y_text = ", ".join(str(int(v) if v == int(v) else v) for v in ys)

    return RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.96,
        layout_mode="dense_matrix",
        x_grid_positions_mm=xs,
        y_grid_positions_mm=ys,
        column_placements=placements,
        detected_parameters=[
            DetectedParameterEntry(key="grid_extraction_source", value="grid_model_editor"),
            DetectedParameterEntry(key="x_grid_text", value=x_text),
            DetectedParameterEntry(key="y_grid_text", value=y_text),
            DetectedParameterEntry(key="column_profile", value=column_profile),
        ],
        notes="; ".join(model.notes + ["GridModel → explicit column placements (no re-snap)."]),
    )

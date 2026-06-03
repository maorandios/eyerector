"""Align AI-extracted coordinates to a consistent plan grid (single sheet)."""

from __future__ import annotations

import os

from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec


def _snap(value: float, grid_mm: float) -> float:
    if grid_mm <= 0:
        return value
    return round(value / grid_mm) * grid_mm


def align_pure_model_for_display(model: PureStructuralModelSpec) -> tuple[PureStructuralModelSpec, list[str]]:
    """
    Move model origin to (0,0,0) and snap endpoints to a regular grid so the IFC view
  matches the plan layout more closely.
    """
    warnings: list[str] = []
    try:
        grid_mm = float(os.getenv("PDF_GRID_SNAP_MM", "100"))
    except ValueError:
        grid_mm = 100.0

    if not model.elements:
        return model, warnings

    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for el in model.elements:
        xs.extend((el.start_x, el.end_x))
        ys.extend((el.start_y, el.end_y))
        zs.extend((el.start_z, el.end_z))

    min_x, min_y, min_z = min(xs), min(ys), min(zs)

    aligned: list[PureSteelElementSpec] = []
    for el in model.elements:
        aligned.append(
            el.model_copy(
                update={
                    "start_x": _snap(el.start_x - min_x, grid_mm),
                    "start_y": _snap(el.start_y - min_y, grid_mm),
                    "start_z": _snap(el.start_z - min_z, grid_mm),
                    "end_x": _snap(el.end_x - min_x, grid_mm),
                    "end_y": _snap(el.end_y - min_y, grid_mm),
                    "end_z": _snap(el.end_z - min_z, grid_mm),
                }
            )
        )

    warnings.append(
        f"Aligned model to plan grid ({grid_mm:.0f} mm snap, origin at building min corner)."
    )
    return PureStructuralModelSpec(elements=aligned, slabs=model.slabs), warnings

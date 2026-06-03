"""Detect generic placeholder frames vision invents instead of reading the plan."""

from __future__ import annotations

import math
from dataclasses import dataclass

from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec

Z_VERT_RATIO = 0.9
PLAN_TOL_MM = 150.0


@dataclass
class SchematicCheck:
    is_placeholder: bool
    reason: str = ""


def _segment_vectors(el: PureSteelElementSpec) -> tuple[float, float, float, float]:
    dx = float(el.end_x) - float(el.start_x)
    dy = float(el.end_y) - float(el.start_y)
    dz = float(el.end_z) - float(el.start_z)
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    return dx, dy, dz, length


def _is_vertical(el: PureSteelElementSpec) -> bool:
    _dx, _dy, dz, length = _segment_vectors(el)
    if length <= 1.0:
        return False
    plan = math.hypot(_dx, _dy)
    return abs(dz) / length >= Z_VERT_RATIO and plan <= PLAN_TOL_MM


def _column_base(el: PureSteelElementSpec) -> tuple[int, int]:
    def q(v: float) -> int:
        return int(round(v / 500.0))

    z0 = min(float(el.start_z), float(el.end_z))
    if float(el.start_z) <= float(el.end_z) + 1:
        return q(float(el.start_x)), q(float(el.start_y))
    return q(float(el.end_x)), q(float(el.end_y))


def detect_schematic_placeholder(
    model: PureStructuralModelSpec,
    *,
    dense_cad: bool,
    max_members: int = 24,
) -> SchematicCheck:
    """
    Vision on unreadable CAD often returns a fake 4-column portal + perimeter beams (~8–16 members).
    """
    n = len(model.elements)
    if not dense_cad or n < 6 or n > max_members:
        return SchematicCheck(False)

    verticals = [el for el in model.elements if _is_vertical(el)]
    horizontals = [el for el in model.elements if not _is_vertical(el)]

    if len(verticals) != 4:
        return SchematicCheck(False)

    bases = {_column_base(v) for v in verticals}
    if len(bases) != 4:
        return SchematicCheck(False)

    xs: list[float] = []
    ys: list[float] = []
    for el in model.elements:
        xs.extend((float(el.start_x), float(el.end_x)))
        ys.extend((float(el.start_y), float(el.end_y)))
    span_x = max(xs) - min(xs) if xs else 0.0
    span_y = max(ys) - min(ys) if ys else 0.0
    if span_x < 2000 or span_y < 2000:
        return SchematicCheck(False)

    ratio = span_x / span_y if span_y > 0 else 0.0
    if ratio < 0.35 or ratio > 2.8:
        return SchematicCheck(False)

    # Typical fake model: few horizontals (roof rails / perimeter), no bracing grid
    if len(horizontals) > 14:
        return SchematicCheck(False)

    z_levels = {
        int(round(min(float(el.start_z), float(el.end_z)) / 500.0))
        for el in horizontals
    }
    if len(z_levels) > 4:
        return SchematicCheck(False)

    return SchematicCheck(
        True,
        reason=(
            f"Vision returned a schematic placeholder (~{n} members: 4 corner columns, "
            f"{len(horizontals)} horizontals on a {span_x:.0f}×{span_y:.0f} mm box) — "
            "not geometry from your plan sheet."
        ),
    )

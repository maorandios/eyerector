"""
General geometry compiler: UniversalStructuralIntent → absolute member coordinates.

Placement rules are geometric (axis, grid assignment, levels) — not building-type templates.
Output is converted to PureStructuralModelSpec before IFC.
"""

from __future__ import annotations

from analyzer_service.geometry_assignments import (
    coerce_diagonal_assignment,
    coerce_horizontal_x_assignment,
    coerce_horizontal_y_assignment,
    coerce_vertical_assignment,
)
from analyzer_service.schemas import (
    GridFrameSpec,
    IndependentElementSpec,
    SlabGroupSpec,
    StructuralGroupSpec,
    StructuralIntentIR,
    UniversalStructuralIntent,
)


class GridFrameCompileError(Exception):
    """Raised when neutral intent cannot be compiled to coordinates."""


def _level_map(intent: UniversalStructuralIntent) -> dict[str, float]:
    return {level.name: float(level.elevation_mm) for level in intent.levels}


def _z(levels: dict[str, float], name: str) -> float:
    if name not in levels:
        raise GridFrameCompileError(f"Unknown level reference: {name}")
    return levels[name]


def _x_grid(grid: GridFrameSpec) -> list[float]:
    if grid.frame_line_x_mm:
        lines = sorted(float(x) for x in grid.frame_line_x_mm)
        if len(lines) >= 2:
            return lines
    length = float(grid.length_x_mm)
    bay = float(grid.bay_spacing_x_mm)
    n_bays = max(1, int(round(length / bay)))
    return [i * (length / n_bays) for i in range(n_bays + 1)]


def _y_lines(grid: GridFrameSpec) -> list[float]:
    if grid.frame_line_y_mm:
        return [float(y) for y in grid.frame_line_y_mm]
    return [0.0, float(grid.width_y_mm)]


def _ridge_y_mm(grid: GridFrameSpec, width: float) -> float:
    """Ridge line Y: mid-span grid line when present, else half building width."""
    lines = _y_lines(grid)
    if len(lines) >= 3:
        return float(lines[len(lines) // 2])
    return width / 2.0


def _truss_eave_ridge_heights(
    levels: dict[str, float],
    *,
    z0: float,
    z1: float,
) -> tuple[float, float] | None:
    """
    Resolve bottom (eave) and top (ridge) Z for truss web panels.
    Returns None when a valid sloped truss cannot be inferred (group is skipped).
    """
    named_roof = [levels[name] for name in ("Eave", "ColumnTop", "Ridge", "Apex") if name in levels]
    if len(named_roof) >= 2:
        named_roof.sort()
        eave_h, ridge_h = named_roof[0], named_roof[-1]
        if ridge_h > eave_h + 1e-6:
            return eave_h, ridge_h

    if abs(z1 - z0) > 1e-6:
        return min(z0, z1), max(z0, z1)

    eave_h = levels.get("Eave") or levels.get("ColumnTop")
    ridge_h = levels.get("Ridge") or levels.get("Apex")
    if eave_h is not None and ridge_h is not None and ridge_h > eave_h + 1e-6:
        return float(eave_h), float(ridge_h)

    # Use the two highest non-mezzanine elevations (excludes Level1/2 decks, guardrails).
    skip_prefixes = ("level", "guardrail", "brace")
    structural = sorted(
        {
            float(z)
            for name, z in levels.items()
            if name != "Ground" and not name.casefold().startswith(skip_prefixes)
        }
    )
    if len(structural) >= 2 and structural[-1] > structural[-2] + 1e-6:
        return structural[-2], structural[-1]

    return None


def _roof_z(
    y: float,
    width: float,
    eave_h: float,
    ridge_h: float,
    *,
    ridge_y: float | None = None,
) -> float:
    center = float(ridge_y) if ridge_y is not None else width / 2.0
    if center <= 1e-6 or abs(center - width) <= 1e-6:
        center = width / 2.0
    if y <= center:
        return eave_h + (ridge_h - eave_h) * (y / center)
    span = max(width - center, 1e-6)
    return ridge_h - (ridge_h - eave_h) * ((y - center) / span)


def _is_slab_like_group(group: StructuralGroupSpec) -> bool:
    gid = group.id.casefold()
    if group.category == "slab":
        return True
    if "slab" in gid or "foundation" in gid:
        return True
    if group.assigned_to_grid == "full_grid_footprint":
        return True
    return False


def _filter_x_lines(x_lines: list[float], group: StructuralGroupSpec) -> list[float]:
    filtered = list(x_lines)
    if group.x_min_mm is not None:
        filtered = [x for x in filtered if x >= float(group.x_min_mm) - 0.5]
    if group.x_max_mm is not None:
        filtered = [x for x in filtered if x <= float(group.x_max_mm) + 0.5]
    if not filtered:
        raise GridFrameCompileError(
            f"Group '{group.id}' x range [{group.x_min_mm}, {group.x_max_mm}] excludes all frame lines"
        )
    return filtered


def _resolve_y_lines(y_lines: list[float], group: StructuralGroupSpec) -> list[float]:
    if group.y_at_mm:
        return sorted(float(y) for y in group.y_at_mm)
    return y_lines


def _remap_misassigned_group(
    group: StructuralGroupSpec,
    *,
    level_names: set[str],
) -> StructuralGroupSpec:
    """Correct common LLM orientation/assignment mismatches using geometry-only heuristics."""
    if group.orientation == "truss_web_panels":
        updates: dict[str, str] = {}
        if group.start_level not in level_names:
            updates["start_level"] = (
                "Eave" if "Eave" in level_names else "ColumnTop" if "ColumnTop" in level_names else group.start_level
            )
        if group.end_level not in level_names:
            for candidate in ("Ridge", "Apex", "ColumnTop", "Eave"):
                if candidate in level_names:
                    updates["end_level"] = candidate
                    break
        if group.start_level == group.end_level:
            updates["start_level"] = "Eave" if "Eave" in level_names else group.start_level
            updates["end_level"] = (
                "Ridge"
                if "Ridge" in level_names
                else "Apex"
                if "Apex" in level_names
                else "ColumnTop"
                if "ColumnTop" in level_names
                else group.end_level
            )
        if updates:
            return group.model_copy(update=updates)
    gid = group.id.casefold().replace("-", "_")
    assign = group.assigned_to_grid.casefold().replace("-", "_").replace(" ", "_")
    if group.orientation == "horizontal_y":
        coerced = coerce_horizontal_y_assignment(group.assigned_to_grid)
        known_y = {
            "along_y_at_frame_ends",
            "along_y_per_x_station",
            "distributed_along_x",
            "along_y_at_x_min",
            "along_y_at_x_max",
        }
        if coerced not in known_y and coerced == group.assigned_to_grid.strip().casefold().replace(" ", "_"):
            if any(token in assign for token in ("along_x", "between_column", "between_columns", "x_span")) or (
                "primary" in gid and "beam" in gid
            ):
                return group.model_copy(
                    update={
                        "orientation": "horizontal_x",
                        "assigned_to_grid": "along_x_between_columns",
                    }
                )
            if any(token in assign for token in ("per_x", "each_x", "station", "frame_line")):
                return group.model_copy(update={"assigned_to_grid": "along_y_per_x_station"})
    return group


def _normalize_intent(intent: UniversalStructuralIntent) -> UniversalStructuralIntent:
    """Move misclassified slab groups from groups[] into slabs[]; fix LLM grid assignments."""
    level_names = {level.name for level in intent.levels}
    slabs = list(intent.slabs)
    groups: list[StructuralGroupSpec] = []
    for group in intent.groups:
        group = _remap_misassigned_group(group, level_names=level_names)
        if not _is_slab_like_group(group):
            groups.append(group)
            continue
        top_level = group.end_level if group.end_level in {l.name for l in intent.levels} else group.start_level
        thickness = float(group.spacing_mm or 400.0)
        slabs.append(
            SlabGroupSpec(
                id=group.id,
                top_level=top_level,
                thickness_mm=thickness,
            )
        )
    return intent.model_copy(update={"groups": groups, "slabs": slabs})


def _nearest_line(lines: list[float], target: float) -> float:
    return min(lines, key=lambda value: abs(value - target))


def _y_span_positions(
    width: float,
    spacing: float,
    *,
    y_min: float | None,
    y_max: float | None,
) -> list[float]:
    y_lo = float(y_min) if y_min is not None else 0.0
    y_hi = float(y_max) if y_max is not None else float(width)
    span = max(y_hi - y_lo, 1e-6)
    positions = [y_lo + offset for offset in _distributed_positions(span, spacing)]
    if y_lo <= 1e-6 and y_hi >= width - 1e-6:
        return positions
    return [y for y in positions if y_lo - 1e-6 <= y <= y_hi + 1e-6]


def _distributed_positions(span: float, spacing: float) -> list[float]:
    if spacing <= 0:
        raise GridFrameCompileError("spacing_mm must be > 0 for distributed members")
    count = int(round(span / spacing))
    return [i * spacing for i in range(count + 1)]


def _add(
    elements: list[IndependentElementSpec],
    *,
    element_id: str,
    category: str,
    profile: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> None:
    sx, sy, sz = start
    ex, ey, ez = end
    if (
        abs(sx - ex) <= 1e-6
        and abs(sy - ey) <= 1e-6
        and abs(sz - ez) <= 1e-6
    ):
        return
    elements.append(
        IndependentElementSpec(
            id=element_id,
            category=category,  # type: ignore[arg-type]
            profile_name=profile,
            start_x=sx,
            start_y=sy,
            start_z=sz,
            end_x=ex,
            end_y=ey,
            end_z=ez,
        )
    )


def _compile_group(
    group: StructuralGroupSpec,
    *,
    grid: GridFrameSpec,
    levels: dict[str, float],
    x_lines: list[float],
    y_lines: list[float],
    elements: list[IndependentElementSpec],
    index: int,
) -> int:
    z0 = _z(levels, group.start_level)
    z1 = _z(levels, group.end_level)
    length = float(grid.length_x_mm)
    width = float(grid.width_y_mm)
    profile = group.profile_name
    gid = group.id

    if group.orientation == "vertical":
        grid_assign = coerce_vertical_assignment(group.assigned_to_grid)
        if grid_assign == "all_frame_lines":
            points = [(x, y) for x in x_lines for y in y_lines]
        elif grid_assign == "perimeter":
            points = [
                (x_lines[0], y_lines[0]),
                (x_lines[-1], y_lines[0]),
                (x_lines[0], y_lines[-1]),
                (x_lines[-1], y_lines[-1]),
            ]
        elif grid_assign == "along_all_x_at_y_min":
            points = [(x, y_lines[0]) for x in x_lines]
        elif grid_assign == "along_all_x_at_y_max":
            points = [(x, y_lines[-1]) for x in x_lines]
        else:
            raise GridFrameCompileError(
                f"Group '{gid}' vertical members need all_frame_lines, perimeter, "
                f"along_all_x_at_y_min, or along_all_x_at_y_max (got '{group.assigned_to_grid}')"
            )
        for i, (x, y) in enumerate(points, start=1):
            _add(
                elements,
                element_id=f"{gid}_{index + i}",
                category="column",
                profile=profile,
                start=(x, y, z0),
                end=(x, y, z1),
            )
        return index + len(points)

    if group.orientation == "horizontal_x":
        grid_assign = coerce_horizontal_x_assignment(group.assigned_to_grid)
        if grid_assign == "distributed_along_y":
            spacing = group.spacing_mm
            if spacing is None:
                raise GridFrameCompileError(f"Group '{gid}' distributed_along_y requires spacing_mm")
            ys = _y_span_positions(
                width,
                spacing,
                y_min=group.y_min_mm,
                y_max=group.y_max_mm,
            )
            xs = _filter_x_lines(x_lines, group)
            for i, y in enumerate(ys, start=1):
                _add(
                    elements,
                    element_id=f"{gid}_{index + i}",
                    category=group.category,
                    profile=profile,
                    start=(xs[0], y, z0),
                    end=(xs[-1], y, z1),
                )
            return index + len(ys)
        if grid_assign == "along_x_at_y_max":
            xs = _filter_x_lines(x_lines, group)
            _add(
                elements,
                element_id=f"{gid}_{index + 1}",
                category=group.category,
                profile=profile,
                start=(xs[0], y_lines[-1], z0),
                end=(xs[-1], y_lines[-1], z1),
            )
            return index + 1
        if grid_assign == "along_x_at_fixed_y":
            xs = _filter_x_lines(x_lines, group)
            y_station = float(group.y_min_mm) if group.y_min_mm is not None else y_lines[0]
            if group.y_max_mm is not None:
                y_station = float(group.y_max_mm)
            _add(
                elements,
                element_id=f"{gid}_{index + 1}",
                category=group.category,
                profile=profile,
                start=(xs[0], y_station, z0),
                end=(xs[-1], y_station, z1),
            )
            return index + 1
        if grid_assign not in ("along_x_between_columns", "along_x_at_each_y_line"):
            raise GridFrameCompileError(
                f"Group '{gid}' horizontal_x requires along_x_between_columns, "
                f"along_x_at_each_y_line, or distributed_along_y"
            )
        n = 0
        xs = _filter_x_lines(x_lines, group)
        member_limit = group.member_count
        for y in _resolve_y_lines(y_lines, group):
            for i in range(1, len(xs)):
                if member_limit is not None and n >= member_limit:
                    return index + n
                n += 1
                _add(
                    elements,
                    element_id=f"{gid}_{index + n}",
                    category=group.category,
                    profile=profile,
                    start=(xs[i - 1], y, z0),
                    end=(xs[i], y, z1),
                )
        return index + n

    if group.orientation == "horizontal_y_per_frame":
        n = 0
        for x in _filter_x_lines(x_lines, group):
            n += 1
            _add(
                elements,
                element_id=f"{gid}_{index + n}",
                category=group.category,
                profile=profile,
                start=(x, y_lines[0], z0),
                end=(x, y_lines[-1], z1),
            )
        return index + n

    if group.orientation == "horizontal_y":
        grid_assign = coerce_horizontal_y_assignment(group.assigned_to_grid)
        y_start = float(group.y_from_mm) if group.y_from_mm is not None else y_lines[0]
        y_end = float(group.y_to_mm) if group.y_to_mm is not None else y_lines[-1]
        if grid_assign == "along_y_per_x_station":
            for i, x in enumerate(_filter_x_lines(x_lines, group), start=1):
                _add(
                    elements,
                    element_id=f"{gid}_{index + i}",
                    category=group.category,
                    profile=profile,
                    start=(x, y_start, z0),
                    end=(x, y_end, z1),
                )
            return index + len(_filter_x_lines(x_lines, group))
        if grid_assign == "along_y_at_frame_ends":
            n = 0
            for x in (x_lines[0], x_lines[-1]):
                n += 1
                _add(
                    elements,
                    element_id=f"{gid}_{index + n}",
                    category=group.category,
                    profile=profile,
                    start=(x, y_lines[0], z0),
                    end=(x, y_lines[-1], z1),
                )
            return index + n
        if grid_assign == "distributed_along_x":
            spacing = group.spacing_mm
            if spacing is None:
                raise GridFrameCompileError(f"Group '{gid}' requires spacing_mm")
            span_start = float(group.x_min_mm) if group.x_min_mm is not None else 0.0
            span_end = float(group.x_max_mm) if group.x_max_mm is not None else length
            xs = [span_start + offset for offset in _distributed_positions(span_end - span_start, spacing)]
            for i, x in enumerate(xs, start=1):
                _add(
                    elements,
                    element_id=f"{gid}_{index + i}",
                    category=group.category,
                    profile=profile,
                    start=(x, y_start, z0),
                    end=(x, y_end, z1),
                )
            return index + len(xs)
        if grid_assign == "along_y_at_x_min":
            _add(
                elements,
                element_id=f"{gid}_{index + 1}",
                category=group.category,
                profile=profile,
                start=(x_lines[0], y_lines[0], z0),
                end=(x_lines[0], y_lines[-1], z1),
            )
            return index + 1
        if grid_assign == "along_y_at_x_max":
            _add(
                elements,
                element_id=f"{gid}_{index + 1}",
                category=group.category,
                profile=profile,
                start=(x_lines[-1], y_lines[0], z0),
                end=(x_lines[-1], y_lines[-1], z1),
            )
            return index + 1
        if grid_assign == "along_y_at_fixed_x":
            if group.x_min_mm is None:
                raise GridFrameCompileError(f"Group '{gid}' along_y_at_fixed_x requires x_min_mm")
            x_station = _nearest_line(_filter_x_lines(x_lines, group), float(group.x_min_mm))
            y_start = float(group.y_min_mm) if group.y_min_mm is not None else y_lines[0]
            y_end = float(group.y_max_mm) if group.y_max_mm is not None else y_lines[-1]
            _add(
                elements,
                element_id=f"{gid}_{index + 1}",
                category=group.category,
                profile=profile,
                start=(x_station, y_start, z0),
                end=(x_station, y_end, z1),
            )
            return index + 1
        raise GridFrameCompileError(
            f"Group '{gid}' horizontal_y requires along_y_at_frame_ends, "
            f"distributed_along_x, along_y_per_x_station, along_y_at_x_min, along_y_at_x_max, "
            f"or along_y_at_fixed_x"
        )

    if group.orientation == "inclined_y":
        for i, x in enumerate(x_lines, start=1):
            _add(
                elements,
                element_id=f"{gid}_{index + i}",
                category=group.category,
                profile=profile,
                start=(x, y_lines[0], z0),
                end=(x, y_lines[-1], z1),
            )
        return index + len(x_lines)

    if group.orientation == "inclined_dual_y":
        half = _ridge_y_mm(grid, width)
        ridge_z = _z(levels, "Ridge") if "Ridge" in levels else z1
        eave_z = _z(levels, "Eave") if "Eave" in levels else z0
        for i, x in enumerate(_filter_x_lines(x_lines, group), start=1):
            _add(
                elements,
                element_id=f"{gid}_left_{index + i}",
                category=group.category,
                profile=profile,
                start=(x, 0.0, eave_z),
                end=(x, half, ridge_z),
            )
            _add(
                elements,
                element_id=f"{gid}_right_{index + i}",
                category=group.category,
                profile=profile,
                start=(x, half, ridge_z),
                end=(x, width, eave_z),
            )
        return index + len(x_lines) * 2

    if group.orientation == "truss_web_panels":
        spacing = float(group.spacing_mm or 2500.0)
        heights = _truss_eave_ridge_heights(levels, z0=z0, z1=z1)
        if heights is None:
            return index
        eave_h, ridge_h = heights
        warren = "warren" in group.assigned_to_grid.casefold() or "warren" in gid
        panels = int(
            group.member_count
            if group.member_count
            else max(4, int(round(width / max(spacing, 1.0))))
        )
        panels = max(panels, 2)
        y_nodes = [width * i / panels for i in range(panels + 1)]
        n = 0
        ridge_y = _ridge_y_mm(grid, width)
        for x in _filter_x_lines(x_lines, group):
            if not warren:
                for y in y_nodes[1:-1]:
                    top_z = _roof_z(y, width, eave_h, ridge_h, ridge_y=ridge_y)
                    if abs(top_z - eave_h) <= 1e-6:
                        continue
                    n += 1
                    _add(
                        elements,
                        element_id=f"{gid}_v_{index + n}",
                        category=group.category,
                        profile=profile,
                        start=(x, y, eave_h),
                        end=(x, y, top_z),
                    )
            panel_count = panels if warren else len(y_nodes) - 1
            for i in range(panel_count):
                y0 = y_nodes[i]
                y1 = y_nodes[i + 1] if i + 1 < len(y_nodes) else width
                z1_roof = _roof_z(y1, width, eave_h, ridge_h, ridge_y=ridge_y)
                z0_roof = _roof_z(y0, width, eave_h, ridge_h, ridge_y=ridge_y)
                if warren:
                    if i % 2 == 0:
                        start = (x, y0, eave_h)
                        end = (x, y1, z1_roof)
                    elif z0_roof > eave_h + 1e-6:
                        start = (x, y0, z0_roof)
                        end = (x, y1, eave_h)
                    else:
                        start = (x, y0, eave_h)
                        end = (x, y1, z1_roof)
                elif i % 2 == 0:
                    start = (x, y0, eave_h)
                    end = (x, y1, z1_roof)
                else:
                    start = (x, y1, eave_h)
                    end = (x, y0, z0_roof)
                if (
                    abs(start[0] - end[0]) <= 1e-6
                    and abs(start[1] - end[1]) <= 1e-6
                    and abs(start[2] - end[2]) <= 1e-6
                ):
                    continue
                n += 1
                _add(
                    elements,
                    element_id=f"{gid}_d_{index + n}",
                    category=group.category,
                    profile=profile,
                    start=start,
                    end=end,
                )
        return index + n

    if group.orientation == "roof_purlins_dual_slope":
        eave_h = _z(levels, "Eave") if "Eave" in levels else z0
        ridge_h = _z(levels, "Ridge") if "Ridge" in levels else z1
        ridge_y = _ridge_y_mm(grid, width)
        lines_per_slope = int(group.member_count or 6)
        n = 0
        for i in range(1, lines_per_slope + 1):
            y_left = ridge_y * (i / (lines_per_slope + 1))
            z_left = _roof_z(y_left, width, eave_h, ridge_h, ridge_y=ridge_y)
            n += 1
            _add(
                elements,
                element_id=f"{gid}_left_{index + n}",
                category=group.category,
                profile=profile,
                start=(0.0, y_left, z_left),
                end=(length, y_left, z_left),
            )
            y_right = ridge_y + (width - ridge_y) * (i / (lines_per_slope + 1))
            z_right = _roof_z(y_right, width, eave_h, ridge_h, ridge_y=ridge_y)
            n += 1
            _add(
                elements,
                element_id=f"{gid}_right_{index + n}",
                category=group.category,
                profile=profile,
                start=(0.0, y_right, z_right),
                end=(length, y_right, z_right),
            )
        return index + n

    if group.orientation == "wall_girts_fixed_z":
        elevations = group.fixed_elevations_mm or [1500.0, 3000.0, 4500.0, 5800.0]
        n = 0
        for z in elevations:
            for y in (y_lines[0], y_lines[-1]):
                n += 1
                _add(
                    elements,
                    element_id=f"{gid}_{index + n}",
                    category=group.category,
                    profile=profile,
                    start=(0.0, y, float(z)),
                    end=(length, y, float(z)),
                )
        return index + n

    if group.orientation == "diagonal_plan":
        offset = float(group.brace_offset_x_mm or 1000.0)
        targets: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
        grid_assign = coerce_diagonal_assignment(group.assigned_to_grid)
        if grid_assign == "per_x_station":
            y_start = float(group.y_from_mm) if group.y_from_mm is not None else y_lines[0]
            y_end = float(group.y_to_mm) if group.y_to_mm is not None else y_lines[-1]
            for x in _filter_x_lines(x_lines, group):
                targets.append(((x, y_start, z0), (x, y_end, z1)))
        elif grid_assign == "first_and_last_bay_braces":
            if len(x_lines) < 2:
                raise GridFrameCompileError(f"Group '{gid}' needs at least two frame lines for bay bracing")
            bay_pairs = [(x_lines[0], x_lines[1]), (x_lines[-2], x_lines[-1])]
            for x_start, x_end in bay_pairs:
                for y in y_lines:
                    targets.append(((x_start, y, z0), (x_end, y, z1)))
        elif grid_assign == "corner_braces":
            corners = [
                (x_lines[0], y_lines[0]),
                (x_lines[0], y_lines[-1]),
                (x_lines[-1], y_lines[0]),
                (x_lines[-1], y_lines[-1]),
            ]
            for x, y in corners:
                ex = min(length, x + offset) if x == x_lines[0] else max(0.0, x - offset)
                targets.append(((x, y, z0), (ex, y, z1)))
        elif grid_assign == "roof_truss_diagonals":
            eave_h = _z(levels, "Eave") if "Eave" in levels else z0
            ridge_h = _z(levels, "Ridge") if "Ridge" in levels else z1
            ridge_y = _ridge_y_mm(grid, width)
            frame_xs = [x_lines[0], x_lines[len(x_lines) // 2], x_lines[-1]]
            for x in frame_xs:
                targets.append(((x, 0.0, eave_h), (x, ridge_y, ridge_h)))
                targets.append(((x, ridge_y, ridge_h), (x, width, eave_h)))
        else:
            raise GridFrameCompileError(
                f"Group '{gid}' diagonal_plan requires corner_braces, first_and_last_bay_braces, "
                f"roof_truss_diagonals, or per_x_station"
            )
        for i, (start, end) in enumerate(targets, start=1):
            _add(
                elements,
                element_id=f"{gid}_{index + i}",
                category="brace",
                profile=profile,
                start=start,
                end=end,
            )
        return index + len(targets)

    raise GridFrameCompileError(f"Unsupported orientation '{group.orientation}' in group '{gid}'")


def compile_universal_intent_to_ir(intent: UniversalStructuralIntent) -> StructuralIntentIR:
    intent = _normalize_intent(intent)
    levels = _level_map(intent)
    grid = intent.grid
    x_lines = _x_grid(grid)
    y_lines = _y_lines(grid)
    elements: list[IndependentElementSpec] = []
    counter = 0

    for group in intent.groups:
        counter = _compile_group(
            group,
            grid=grid,
            levels=levels,
            x_lines=x_lines,
            y_lines=y_lines,
            elements=elements,
            index=counter,
        )

    for slab in intent.slabs:
        top_z = _z(levels, slab.top_level)
        bottom_z = top_z - float(slab.thickness_mm)
        x0 = float(slab.x_min_mm) if slab.x_min_mm is not None else 0.0
        x1 = float(slab.x_max_mm) if slab.x_max_mm is not None else float(grid.length_x_mm)
        y0 = float(slab.y_min_mm) if slab.y_min_mm is not None else 0.0
        y1 = float(slab.y_max_mm) if slab.y_max_mm is not None else float(grid.width_y_mm)
        if slab.footprint not in ("full_grid", "partial_xy"):
            raise GridFrameCompileError(f"Unsupported slab footprint: {slab.footprint}")
        _add(
            elements,
            element_id=slab.id,
            category="slab",
            profile="CONCRETE_SLAB",
            start=(x0, y0, bottom_z),
            end=(x1, y1, top_z),
        )

    if not elements:
        raise GridFrameCompileError("UniversalStructuralIntent produced no members")
    return StructuralIntentIR(independent_elements=elements)

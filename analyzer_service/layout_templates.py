"""
Deterministic layout templates: ParametricLayoutRequest -> StructuralModelSpec.

All member positions and lengths are computed here — never by the LLM.
"""

from __future__ import annotations

from analyzer_service.catalog_apply import apply_catalog_to_spec
from analyzer_service.schemas import ParametricLayoutRequest, Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.steel_catalog import ResolvedProfile, resolve_profile_key

Z_EPS_MM = 0.5


class LayoutCompilationError(Exception):
    """Raised when a layout cannot be compiled."""


def _column_x_positions(*, column_count: int, total_length_mm: float) -> list[float]:
    """
    Evenly space columns from X=0 to X=total_length_mm.

    spacing = total_length_mm / (column_count - 1)
    For N=3 over 6000mm -> [0, 3000, 6000].
    """
    if column_count < 2:
        raise LayoutCompilationError("column_count must be >= 2 for column_row / portal_frame")

    if column_count == 1:
        return [0.0]

    spacing = total_length_mm / (column_count - 1)
    return [i * spacing for i in range(column_count)]


def _resolved_element(
    *,
    element_type: str,
    profile_name: str,
    length_mm: float,
    position: Position3D,
    beam_axis: str = "X",
) -> StructuralElement:
    resolved: ResolvedProfile = resolve_profile_key(profile_name)
    return StructuralElement(
        type=element_type,  # type: ignore[arg-type]
        profile_type=resolved.profile_type,
        profile_key=resolved.profile_key,
        dimensions=list(resolved.dimensions),
        length_mm=length_mm,
        position=position,
        beam_axis=beam_axis,  # type: ignore[arg-type]
    )


def _compile_column_row(request: ParametricLayoutRequest) -> StructuralModelSpec:
    """
    Column row template:
    - spacing = total_length_mm / (column_count - 1)
    - column i at (x=i*spacing, 0, 0), extruded vertically by height_mm
    """
    n_cols = request.column_count
    span_mm = request.total_length_mm
    height_mm = request.height_mm

    x_positions = _column_x_positions(column_count=n_cols, total_length_mm=span_mm)

    column_profile = request.resolved_column_profile()

    elements: list[StructuralElement] = []
    for x in x_positions:
        elements.append(
            _resolved_element(
                element_type="column",
                profile_name=column_profile,
                length_mm=height_mm,
                position=Position3D(x=x, y=0.0, z=0.0),
            )
        )

    spec = StructuralModelSpec(elements=elements)
    return apply_catalog_to_spec(spec)


def _compile_portal_frame(request: ParametricLayoutRequest) -> StructuralModelSpec:
    """
    Portal frame template:
    - column row at Z=0 with height_mm
    - beam local origin at (0, 0, height_mm), extruded horizontally by total_length_mm
    """
    base = _compile_column_row(request)
    height_mm = request.height_mm

    beam = _resolved_element(
        element_type="beam",
        profile_name=request.resolved_beam_profile(),
        length_mm=request.total_length_mm,
        position=Position3D(x=0.0, y=0.0, z=height_mm),
        beam_axis="X",
    )

    spec = StructuralModelSpec(elements=[*base.elements, beam])
    return apply_catalog_to_spec(spec)


def _compile_single_element(request: ParametricLayoutRequest) -> StructuralModelSpec:
    element = _resolved_element(
        element_type="column",
        profile_name=request.profile_name,
        length_mm=request.height_mm,
        position=Position3D(),
    )

    spec = StructuralModelSpec(elements=[element])
    return apply_catalog_to_spec(spec)


def _compile_steel_shed(request: ParametricLayoutRequest) -> StructuralModelSpec:
    """
    Steel shed template:
    - 6 columns: corners + long-side midpoints
    - 3 rafters along width (Y), one per column pair (X = 0, L/2, L)
    - N purlins along length (X), on top of rafters, evenly spaced across width
    - 4 base beams around perimeter
    """
    length_mm = request.total_length_mm
    width_mm = request.width_mm
    height_mm = request.height_mm
    purlin_count = request.purlin_count

    x_lines = [0.0, length_mm / 2.0, length_mm]
    col_profile = request.resolved_column_profile()
    rafter_profile = request.resolved_rafter_profile()
    purlin_profile = request.resolved_purlin_profile()
    base_profile = request.resolved_base_beam_profile()

    elements: list[StructuralElement] = []

    # Columns at y=0 and y=width on each frame line.
    for x in x_lines:
        for y in (0.0, width_mm):
            elements.append(
                _resolved_element(
                    element_type="column",
                    profile_name=col_profile,
                    length_mm=height_mm,
                    position=Position3D(x=x, y=y, z=0.0),
                )
            )

    # Rafters span shed width.
    for x in x_lines:
        elements.append(
            _resolved_element(
                element_type="beam",
                profile_name=rafter_profile,
                length_mm=width_mm,
                position=Position3D(x=x, y=0.0, z=height_mm),
                beam_axis="Y",
            )
        )

    # Purlins run along shed length, distributed across width.
    if purlin_count == 1:
        y_positions = [width_mm / 2.0]
    else:
        spacing = width_mm / (purlin_count + 1)
        y_positions = [(i + 1) * spacing for i in range(purlin_count)]
    for y in y_positions:
        elements.append(
            _resolved_element(
                element_type="beam",
                profile_name=purlin_profile,
                length_mm=length_mm,
                position=Position3D(x=0.0, y=y, z=height_mm),
                beam_axis="X",
            )
        )

    # Perimeter/base beams at Z=0.
    elements.append(
        _resolved_element(
            element_type="beam",
            profile_name=base_profile,
            length_mm=length_mm,
            position=Position3D(x=0.0, y=0.0, z=0.0),
            beam_axis="X",
        )
    )
    elements.append(
        _resolved_element(
            element_type="beam",
            profile_name=base_profile,
            length_mm=length_mm,
            position=Position3D(x=0.0, y=width_mm, z=0.0),
            beam_axis="X",
        )
    )
    elements.append(
        _resolved_element(
            element_type="beam",
            profile_name=base_profile,
            length_mm=width_mm,
            position=Position3D(x=0.0, y=0.0, z=0.0),
            beam_axis="Y",
        )
    )
    elements.append(
        _resolved_element(
            element_type="beam",
            profile_name=base_profile,
            length_mm=width_mm,
            position=Position3D(x=length_mm, y=0.0, z=0.0),
            beam_axis="Y",
        )
    )

    spec = StructuralModelSpec(elements=elements)
    return apply_catalog_to_spec(spec)


def compile_layout_to_spec(request: ParametricLayoutRequest) -> StructuralModelSpec:
    """Compile parametric intent into a fully positioned structural model."""
    if request.layout_type == "column_row":
        return _compile_column_row(request)
    if request.layout_type == "portal_frame":
        return _compile_portal_frame(request)
    if request.layout_type == "single_element":
        return _compile_single_element(request)
    if request.layout_type == "steel_shed":
        return _compile_steel_shed(request)
    raise LayoutCompilationError(f"Unknown layout_type: {request.layout_type}")

"""Map region vision output to UniversalStructuralIntent for grid_frame_compiler."""

from __future__ import annotations

from analyzer_service.region_analysis_schemas import JsonValue, RegionStructuralAnalysis
from analyzer_service.region_layout_compiler import (
    _parse_mm_list,
    resolve_column_placements,
    uses_explicit_layout,
)
from analyzer_service.schemas import (
    GridFrameSpec,
    LevelSpec,
    SlabGroupSpec,
    StructuralGroupSpec,
    UniversalStructuralIntent,
)


class UnsupportedElementError(Exception):
    """Raised when element_type cannot be compiled yet."""


def _num(params: dict[str, JsonValue], key: str, default: float) -> float:
    val = params.get(key)
    if val is None:
        return default
    if isinstance(val, bool):
        return float(val)
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def _str(params: dict[str, JsonValue], key: str, default: str) -> str:
    val = params.get(key)
    if val is None:
        return default
    return str(val).strip() or default


def _int(params: dict[str, JsonValue], *keys: str, default: int = 0) -> int:
    for key in keys:
        val = params.get(key)
        if val is None:
            continue
        try:
            return max(0, int(float(str(val).strip().replace(",", ""))))
        except ValueError:
            continue
    return default


def _resolve_grid_frame(params: dict[str, JsonValue]) -> GridFrameSpec:
    """
    Build grid dimensions from column counts and bay spacings when present.

    Layout plans often show N×M column grids; without frame_line_y_mm the compiler
    only places columns on Y=0 and Y=width (two rows).
    """
    bay_x = _num(params, "bay_spacing_x_mm", 0.0)
    if bay_x <= 0:
        bay_x = _num(params, "bay_spacing_mm", 4000.0)

    bay_y = _num(params, "bay_spacing_y_mm", 0.0)
    if bay_y <= 0:
        bay_y = _num(params, "grid_spacing_y_mm", 0.0)

    cols_x = _int(
        params,
        "columns_along_x",
        "column_count_x",
        "columns_x",
        "num_columns_x",
    )
    cols_y = _int(
        params,
        "columns_along_y",
        "column_count_y",
        "columns_y",
        "num_columns_y",
        "frames_along_y",
    )
    bays_x = _int(params, "bays_x", "bay_count_x", "bays_along_x")
    bays_y = _int(params, "bays_y", "bay_count_y", "bays_along_y")

    length_x = _num(params, "length_x_mm", 0.0)
    width_y = _num(params, "width_y_mm", 0.0)

    if cols_x >= 2 and bay_x > 0:
        length_x = (cols_x - 1) * bay_x
    elif bays_x >= 1 and bay_x > 0:
        length_x = bays_x * bay_x
        cols_x = bays_x + 1
    elif length_x > 0 and bay_x > 0:
        bays_x = max(1, int(round(length_x / bay_x)))
        length_x = bays_x * bay_x
    else:
        length_x = length_x if length_x > 0 else 12000.0
        bay_x = bay_x if bay_x > 0 else 4000.0

    frame_x: list[float] | None = None
    xs_from_params = _parse_mm_list(params.get("grid_lines_x_mm") or params.get("x_grid_positions_mm"))
    if len(xs_from_params) >= 2:
        frame_x = xs_from_params
        length_x = xs_from_params[-1]
        if len(xs_from_params) >= 2:
            bay_x = xs_from_params[1] - xs_from_params[0]

    frame_y: list[float] | None = None
    ys_from_params = _parse_mm_list(params.get("grid_lines_y_mm") or params.get("y_grid_positions_mm"))
    if len(ys_from_params) >= 2:
        frame_y = ys_from_params
        width_y = ys_from_params[-1]

    if cols_y >= 2 and frame_y is None:
        if bay_y > 0:
            frame_y = [float(i * bay_y) for i in range(cols_y)]
            width_y = (cols_y - 1) * bay_y
        elif width_y > 0:
            step = width_y / (cols_y - 1)
            frame_y = [float(i * step) for i in range(cols_y)]
        else:
            bay_y = bay_y if bay_y > 0 else bay_x
            frame_y = [float(i * bay_y) for i in range(cols_y)]
            width_y = (cols_y - 1) * bay_y
    elif bays_y >= 1:
        spacing = bay_y if bay_y > 0 else bay_x
        frame_y = [float(i * spacing) for i in range(bays_y + 1)]
        width_y = bays_y * spacing
    else:
        width_y = width_y if width_y > 0 else 6000.0

    return GridFrameSpec(
        length_x_mm=length_x,
        width_y_mm=width_y,
        bay_spacing_x_mm=bay_x,
        frame_line_x_mm=frame_x,
        frame_line_y_mm=frame_y,
    )


def _merged_params(
    analysis: RegionStructuralAnalysis,
    overrides: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    merged = analysis.parameters_dict()
    if overrides:
        merged.update(overrides)
    return merged


def map_region_analysis_to_intent(
    analysis: RegionStructuralAnalysis,
    overrides: dict[str, JsonValue] | None = None,
) -> UniversalStructuralIntent:
    params = _merged_params(analysis, overrides)
    element_type = analysis.element_type

    if element_type == "staircase":
        raise UnsupportedElementError(
            "Staircase compilation is not supported yet. Detection only — adjust crop or use AI Designer."
        )
    if element_type == "unknown":
        raise UnsupportedElementError(
            analysis.notes or "Could not classify this region. Try a larger or clearer crop."
        )
    if element_type == "grid":
        return _map_grid(params)
    if element_type == "truss":
        return _map_truss(params)
    if element_type == "mezzanine":
        return _map_mezzanine(params)
    raise UnsupportedElementError(f"Unsupported element_type: {element_type}")


def compile_supported_for_type(element_type: str) -> bool:
    return element_type in ("grid", "truss", "mezzanine")


def _map_grid(params: dict[str, JsonValue]) -> UniversalStructuralIntent:
    grid = _resolve_grid_frame(params)
    eave = _num(params, "eave_height_mm", 6000.0)
    col_profile = _str(params, "column_profile", "HEB200")
    beam_profile = _str(params, "beam_profile", "IPE200")

    return UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
            LevelSpec(name="Eave", elevation_mm=eave),
        ],
        grid=grid,
        groups=[
            StructuralGroupSpec(
                id="columns",
                profile_name=col_profile,
                orientation="vertical",
                assigned_to_grid="all_frame_lines",
                start_level="Ground",
                end_level="Eave",
                category="column",
            ),
            StructuralGroupSpec(
                id="beams_x",
                profile_name=beam_profile,
                orientation="horizontal_x",
                assigned_to_grid="along_x_between_columns",
                start_level="Eave",
                end_level="Eave",
                category="beam",
            ),
            StructuralGroupSpec(
                id="beams_y",
                profile_name=beam_profile,
                orientation="horizontal_y",
                assigned_to_grid="along_x_between_columns",
                start_level="Eave",
                end_level="Eave",
                category="beam",
            ),
        ],
        slabs=[],
    )


def _map_truss(params: dict[str, JsonValue]) -> UniversalStructuralIntent:
    length_x = _num(params, "length_x_mm", 24000.0)
    width_y = _num(params, "width_y_mm", 12000.0)
    bay = _num(params, "bay_spacing_x_mm", 6000.0)
    eave = _num(params, "eave_height_mm", 6000.0)
    ridge = _num(params, "ridge_height_mm", max(eave + 1500.0, 7500.0))
    col_profile = _str(params, "column_profile", "HEB300")
    top = _str(params, "top_chord_profile", "IPE270")
    bottom = _str(params, "bottom_chord_profile", "UPN240")
    web = _str(params, "web_profile", "RHS80x80x5")
    purlin = _str(params, "purlin_profile", "Z200x2.0")

    return UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
            LevelSpec(name="Eave", elevation_mm=eave),
            LevelSpec(name="Ridge", elevation_mm=ridge),
        ],
        grid=GridFrameSpec(
            length_x_mm=length_x,
            width_y_mm=width_y,
            bay_spacing_x_mm=bay,
        ),
        groups=[
            StructuralGroupSpec(
                id="main_columns",
                profile_name=col_profile,
                orientation="vertical",
                assigned_to_grid="all_frame_lines",
                start_level="Ground",
                end_level="Eave",
                category="column",
            ),
            StructuralGroupSpec(
                id="top_chords",
                profile_name=top,
                orientation="inclined_dual_y",
                assigned_to_grid="along_y_per_frame_line",
                start_level="Eave",
                end_level="Ridge",
                category="beam",
            ),
            StructuralGroupSpec(
                id="bottom_chords",
                profile_name=bottom,
                orientation="horizontal_y",
                assigned_to_grid="along_y_per_frame_line",
                start_level="Eave",
                end_level="Eave",
                category="beam",
            ),
            StructuralGroupSpec(
                id="web_members",
                profile_name=web,
                orientation="truss_web_panels",
                assigned_to_grid="all_frame_lines",
                start_level="Eave",
                end_level="Ridge",
                category="beam",
            ),
            StructuralGroupSpec(
                id="purlins",
                profile_name=purlin,
                orientation="roof_purlins_dual_slope",
                assigned_to_grid="distributed_along_x",
                start_level="Ridge",
                end_level="Ridge",
                spacing_mm=1500.0,
                category="beam",
            ),
        ],
        slabs=[
            SlabGroupSpec(
                id="foundation_slab",
                top_level="Ground",
                thickness_mm=400.0,
                footprint="full_grid",
            ),
        ],
    )


def _map_mezzanine(params: dict[str, JsonValue]) -> UniversalStructuralIntent:
    length_x = _num(params, "length_x_mm", 12000.0)
    width_y = _num(params, "width_y_mm", 6000.0)
    deck_z = _num(params, "deck_elevation_mm", 3200.0)
    col_top = max(deck_z - 200.0, 2800.0)
    bay = _num(params, "column_bay_spacing_x_mm", _num(params, "bay_spacing_x_mm", 4000.0))
    slab_t = _num(params, "slab_thickness_mm", 50.0)
    col_profile = _str(params, "column_profile", "HEB200")
    girder = _str(params, "girder_profile", _str(params, "beam_profile", "IPE300"))
    joist = _str(params, "joist_profile", "IPE200")
    joist_spacing = _num(params, "joist_spacing_x_mm", 2000.0)
    joist_count = int(_num(params, "joist_count", max(1.0, length_x / joist_spacing - 1)))

    return UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
            LevelSpec(name="Deck", elevation_mm=deck_z),
        ],
        grid=GridFrameSpec(
            length_x_mm=length_x,
            width_y_mm=width_y,
            bay_spacing_x_mm=bay,
        ),
        groups=[
            StructuralGroupSpec(
                id="support_columns",
                profile_name=col_profile,
                orientation="vertical",
                assigned_to_grid="all_frame_lines",
                start_level="Ground",
                end_level="Deck",
                category="column",
            ),
            StructuralGroupSpec(
                id="main_girders",
                profile_name=girder,
                orientation="horizontal_y",
                assigned_to_grid="along_y_at_frame_ends",
                start_level="Deck",
                end_level="Deck",
                category="beam",
            ),
            StructuralGroupSpec(
                id="floor_joists",
                profile_name=joist,
                orientation="horizontal_x",
                assigned_to_grid="distributed_along_x",
                start_level="Deck",
                end_level="Deck",
                member_count=max(joist_count, 1),
                category="beam",
            ),
        ],
        slabs=[
            SlabGroupSpec(
                id="mezzanine_deck_slab",
                top_level="Deck",
                thickness_mm=slab_t,
                footprint="full_grid",
            ),
        ],
    )

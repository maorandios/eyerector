from __future__ import annotations

import json

from analyzer_service.region_analysis_schemas import (
    ActiveColumnIntersection,
    ColumnMarkProfile,
    ColumnPlacement,
    DetectedParameterEntry,
    RegionStructuralAnalysis,
)
from analyzer_service.pure_vector_compiler import compile_pure_to_spec
from analyzer_service.region_layout_compiler import (
    _normalize_axis_positions,
    _positions_from_analysis,
    map_region_analysis_to_pure_model,
    resolve_column_placements,
)

XS_9 = [0.0, 150.0, 810.0, 1460.0, 3650.0, 7500.0, 11350.0, 15200.0, 19050.0]
YS_10 = [0.0, 200.0, 850.0, 1500.0, 2400.0, 4725.0, 6000.0, 7975.0, 9875.0, 11050.0]


def test_active_column_intersection_schema_json_roundtrip() -> None:
    """Strict OpenAI schema accepts grid_index_x/y and serializes cleanly."""
    sample = ActiveColumnIntersection(
        grid_index_x=3,
        grid_index_y=1,
        mark="C14",
        profile_name="IPE200",
    )
    payload = json.loads(sample.model_dump_json())
    assert payload == {
        "grid_index_x": 3,
        "grid_index_y": 1,
        "mark": "C14",
        "profile_name": "IPE200",
    }
    restored = ActiveColumnIntersection.model_validate(payload)
    assert restored.grid_index_x == 3
    assert restored.grid_index_y == 1


def test_non_uniform_grid_lines_place_all_columns() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        x_grid_positions_mm=[0.0, 8000.0, 15500.0, 21700.0, 30000.0],
        y_grid_positions_mm=[0.0, 6000.0, 12000.0],
        detected_parameters=[],
    )
    placements = resolve_column_placements(analysis)
    xs = sorted({p.x_mm for p in placements})
    ys = sorted({p.y_mm for p in placements})
    assert len(xs) == 5
    assert len(ys) == 3
    assert len(placements) == len(xs) * len(ys)
    pure = map_region_analysis_to_pure_model(analysis)
    assert pure is not None
    assert len(pure.elements) == 15
    xs = sorted({e.start_x for e in pure.elements})
    assert xs == [0.0, 8000.0, 15500.0, 21700.0, 30000.0]


def test_mixed_absolute_and_bay_values_do_not_double_cumulate() -> None:
    stations = _normalize_axis_positions([0.0, 150.0, 810.0, 1460.0, 19050.0])
    assert stations == [0.0, 150.0, 810.0, 1460.0, 19050.0]
    assert stations[-1] == 19050.0
    assert stations[1] - stations[0] == 150.0


def test_contaminated_merge_with_bay_array() -> None:
    """Bay spacings must not be merged into an absolute station list."""
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        x_grid_positions_mm=[0.0, 19050.0],
        y_grid_positions_mm=[0.0, 11050.0],
        x_bay_spacings_mm=[810.0, 650.0, 2810.0, 3850.0],
        y_bay_spacings_mm=[200.0, 650.0, 900.0],
        detected_parameters=[
            DetectedParameterEntry(
                key="grid_lines_x_mm",
                value="0, 19050, 15200, 11350, 7500, 3650, 1460, 810, 150",
            ),
            DetectedParameterEntry(
                key="grid_lines_y_mm",
                value="0, 200, 850, 1500, 2400, 4725, 6000, 7975, 9875, 11050",
            ),
        ],
    )
    placements = resolve_column_placements(analysis)
    xs = sorted({p.x_mm for p in placements})
    ys = sorted({p.y_mm for p in placements})
    assert len(xs) == 9
    assert len(ys) == 10
    assert len(placements) == len(xs) * len(ys)
    assert len(placements) == 90


def test_merge_sparse_vision_array_with_full_parameter_list() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        x_grid_positions_mm=[0.0, 19050.0],
        y_grid_positions_mm=[0.0, 11050.0],
        detected_parameters=[
            DetectedParameterEntry(
                key="grid_lines_x_mm",
                value="0, 19050, 15200, 11350, 7500, 3650, 1460, 810, 150",
            ),
            DetectedParameterEntry(
                key="grid_lines_y_mm",
                value="0, 200, 850, 1500, 2400, 4725, 6000, 7975, 9875, 11050",
            ),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 90
    assert max(p.x_mm for p in placements) == 19050.0


def test_ordered_bay_spacings_rebuild_cumulative() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        x_bay_spacings_mm=[810.0, 650.0, 2810.0, 3850.0],
        y_bay_spacings_mm=[200.0, 650.0, 900.0],
        detected_parameters=[],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 20
    assert placements[-1].x_mm == 810.0 + 650.0 + 2810.0 + 3850.0


def test_partial_column_placements_without_sparse_uses_explicit_list() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        x_grid_positions_mm=[0.0, 150.0, 810.0, 1460.0, 19050.0],
        y_grid_positions_mm=[0.0, 200.0, 850.0, 1500.0, 11050.0],
        column_placements=[
            ColumnPlacement(id="c1", x_mm=0.0, y_mm=0.0, profile_name="HEB200", height_mm=6000.0),
            ColumnPlacement(id="c2", x_mm=19050.0, y_mm=0.0, profile_name="HEB200", height_mm=6000.0),
            ColumnPlacement(id="c3", x_mm=0.0, y_mm=11050.0, profile_name="HEB200", height_mm=6000.0),
        ],
        detected_parameters=[
            DetectedParameterEntry(key="grid_lines_x_mm", value="0, 150, 810, 1460, 19050"),
            DetectedParameterEntry(key="grid_lines_y_mm", value="0, 200, 850, 1500, 11050"),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 3


def test_sparse_intersections_use_grid_indices() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=XS_9,
        y_grid_positions_mm=YS_10,
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0, mark="C1"),
            ActiveColumnIntersection(grid_index_x=2, grid_index_y=0, mark="C2"),
            ActiveColumnIntersection(grid_index_x=3, grid_index_y=1, mark="C3"),
            ActiveColumnIntersection(grid_index_x=5, grid_index_y=2),
            ActiveColumnIntersection(grid_index_x=6, grid_index_y=3),
            ActiveColumnIntersection(grid_index_x=7, grid_index_y=4),
            ActiveColumnIntersection(grid_index_x=8, grid_index_y=5),
            ActiveColumnIntersection(grid_index_x=4, grid_index_y=6),
            ActiveColumnIntersection(grid_index_x=2, grid_index_y=7),
            ActiveColumnIntersection(grid_index_x=1, grid_index_y=8),
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=9),
            ActiveColumnIntersection(grid_index_x=8, grid_index_y=9),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 12
    assert placements[0].x_mm == XS_9[0]
    assert placements[0].y_mm == YS_10[0]
    assert placements[1].x_mm == XS_9[2]
    assert len(placements) != 90


def test_secondary_axis_no_full_row() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=[0.0, 19050.0],
        y_grid_positions_mm=[0.0, 8500.0, 11050.0],
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0, mark="C1"),
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=1, mark="C2"),
            ActiveColumnIntersection(grid_index_x=1, grid_index_y=0, mark="C3"),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 3
    ys = sorted({p.y_mm for p in placements})
    assert ys == [0.0, 8500.0]


def test_profile_by_mark_overrides_default() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=[0.0, 5000.0],
        y_grid_positions_mm=[0.0, 7000.0],
        detected_parameters=[
            DetectedParameterEntry(key="column_profile", value="HEB200"),
        ],
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0, mark="C14"),
            ActiveColumnIntersection(
                grid_index_x=1, grid_index_y=1, mark="C1", profile_name="RHS100X100X5"
            ),
        ],
        column_profile_by_mark=[
            ColumnMarkProfile(mark="C14", profile_name="IPE200"),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 2
    by_mark = {p.mark: p.profile_name for p in placements}
    assert by_mark["C14"] == "IPE200"
    assert by_mark["C1"] == "100x100x5"
    assert placements[1].x_mm == 5000.0
    assert placements[1].y_mm == 7000.0


def test_dense_matrix_fallback_unchanged() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        layout_mode="dense_matrix",
        x_grid_positions_mm=XS_9,
        y_grid_positions_mm=YS_10,
        detected_parameters=[
            DetectedParameterEntry(key="grid_lines_x_mm", value=", ".join(str(int(v)) for v in XS_9)),
            DetectedParameterEntry(key="grid_lines_y_mm", value=", ".join(str(int(v)) for v in YS_10)),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 90


def test_hydrate_profiles_from_detected_parameter_keys() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=[0.0, 5000.0],
        y_grid_positions_mm=[0.0, 7000.0],
        detected_parameters=[
            DetectedParameterEntry(key="column_profile", value="HEB200"),
            DetectedParameterEntry(key="C14", value="IPE200"),
            DetectedParameterEntry(key="C1", value="RHS100X100X5 PLT10*200"),
        ],
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0, mark="C14"),
            ActiveColumnIntersection(grid_index_x=1, grid_index_y=1, mark="C1"),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 2
    by_mark = {p.mark: p.profile_name for p in placements}
    assert by_mark["C14"] == "IPE200"
    assert by_mark["C1"] == "100x100x5"


def test_invalid_grid_index_skipped() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=[0.0, 5000.0],
        y_grid_positions_mm=[0.0, 7000.0],
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0),
            ActiveColumnIntersection(grid_index_x=99, grid_index_y=0),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 1


def test_mixed_profiles_compile_to_distinct_ifc_shapes() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=[0.0, 5000.0],
        y_grid_positions_mm=[0.0, 7000.0],
        detected_parameters=[
            DetectedParameterEntry(key="column_profile", value="HEB200"),
        ],
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0, mark="C14"),
            ActiveColumnIntersection(
                grid_index_x=1, grid_index_y=1, mark="C1", profile_name="RHS100X100X5"
            ),
        ],
        column_profile_by_mark=[
            ColumnMarkProfile(mark="C14", profile_name="IPE200"),
        ],
    )
    pure = map_region_analysis_to_pure_model(analysis)
    assert pure is not None
    profiles = {e.profile_name for e in pure.elements}
    assert "IPE200" in profiles or "ipe200" in {p.lower() for p in profiles}
    assert any("100" in p for p in profiles)
    spec = compile_pure_to_spec(pure)
    types = {e.profile_type for e in spec.elements}
    assert "IPE" in types
    assert "RHS" in types


def test_duplicate_marks_get_unique_ifc_ids() -> None:
    """Same mark at different grid indices must not collide in PureStructuralModelSpec."""
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        layout_mode="sparse_intersections",
        x_grid_positions_mm=[0.0, 5000.0, 10000.0],
        y_grid_positions_mm=[0.0, 7000.0],
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0, mark="C1"),
            ActiveColumnIntersection(grid_index_x=1, grid_index_y=0, mark="C1"),
            ActiveColumnIntersection(grid_index_x=2, grid_index_y=1, mark="C1"),
        ],
    )
    pure = map_region_analysis_to_pure_model(analysis)
    assert pure is not None
    ids = [e.id for e in pure.elements]
    assert len(ids) == len(set(ids))
    assert ids == ["col_0_0", "col_1_0", "col_2_1"]


def test_sparse_endpoints_union_with_full_grid_lines_text() -> None:
    """Vision [0, max] must not win over full grid_lines_* in detected_parameters."""
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.95,
        x_grid_positions_mm=[0.0, 19050.0],
        y_grid_positions_mm=[0.0, 11050.0],
        detected_parameters=[
            DetectedParameterEntry(
                key="grid_lines_x_mm",
                value="0, 19050, 15200, 11350, 7500, 3650, 1460, 810, 150",
            ),
            DetectedParameterEntry(
                key="grid_lines_y_mm",
                value="0, 200, 850, 1500, 2400, 4725, 6000, 7975, 9875, 11050",
            ),
        ],
    )
    xs, ys = _positions_from_analysis(analysis, None)
    assert len(xs) == 9
    assert len(ys) == 10
    assert xs[-1] == 19050.0


def test_bay_spacings_expand_sparse_endpoint_grid() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        x_grid_positions_mm=[0.0, 8220.0],
        x_bay_spacings_mm=[810.0, 650.0, 2810.0, 3850.0],
        y_grid_positions_mm=[0.0, 4725.0],
        y_bay_spacings_mm=[200.0, 650.0, 900.0],
    )
    xs, ys = _positions_from_analysis(analysis, None)
    assert len(xs) == 5
    assert xs[-1] == 810.0 + 650.0 + 2810.0 + 3850.0
    assert len(ys) == 4


def test_grid_lines_from_parameter_string() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.8,
        detected_parameters=[
            DetectedParameterEntry(key="grid_lines_x_mm", value="0, 5000, 11000, 18000"),
            DetectedParameterEntry(key="grid_lines_y_mm", value="0, 7000"),
        ],
    )
    placements = resolve_column_placements(analysis)
    assert len(placements) == 8

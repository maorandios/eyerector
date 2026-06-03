from __future__ import annotations

from analyzer_service.region_analysis_schemas import RegionStructuralAnalysis
from analyzer_service.region_column_clicks import analysis_from_column_clicks, ColumnClick
from analyzer_service.region_layout_compiler import (
    hydrate_analysis_for_compile,
    resolve_column_placements,
)


def test_hydrate_does_not_collapse_click_placements() -> None:
    clicks = [ColumnClick(100.0 + i * 30, 50.0 + i * 10) for i in range(5)]
    analysis = analysis_from_column_clicks(
        clicks,
        crop_width_px=2000,
        crop_height_px=1500,
        mm_per_px=10.0,
        x_grid_positions_mm=[0.0, 5000.0, 10000.0],
        y_grid_positions_mm=[0.0, 5000.0],
        column_profile="RHS100X100X5",
    )
    hydrated = hydrate_analysis_for_compile(analysis, None)
    assert hydrated.layout_mode == "dense_matrix"
    assert len(hydrated.column_placements) == 5
    placements = resolve_column_placements(hydrated, None)
    assert len(placements) == 5

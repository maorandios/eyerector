from __future__ import annotations

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.schemas import GridFrameSpec, LevelSpec, StructuralGroupSpec, UniversalStructuralIntent


def test_truss_web_skipped_when_no_valid_roof_height_pair() -> None:
    intent = UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
            LevelSpec(name="Level1", elevation_mm=3800.0),
            LevelSpec(name="Eave", elevation_mm=12000.0),
            LevelSpec(name="Ridge", elevation_mm=12000.0),
        ],
        grid=GridFrameSpec(length_x_mm=60000.0, width_y_mm=30000.0, bay_spacing_x_mm=6000.0),
        groups=[
            StructuralGroupSpec(
                id="bottom_chord",
                profile_name="HEA220",
                orientation="horizontal_y_per_frame",
                assigned_to_grid="along_y_per_frame_line",
                start_level="Eave",
                end_level="Eave",
                category="beam",
            ),
            StructuralGroupSpec(
                id="web_members",
                profile_name="RHS90x90x6",
                orientation="truss_web_panels",
                assigned_to_grid="all_frame_lines",
                start_level="Eave",
                end_level="Ridge",
                spacing_mm=2500.0,
                category="beam",
            ),
        ],
    )
    ir = compile_universal_intent_to_ir(intent)
    webs = [element for element in ir.independent_elements if element.id.startswith("web_members")]
    assert len(webs) == 0


def test_truss_web_uses_distinct_roof_levels() -> None:
    intent = UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
            LevelSpec(name="Level1", elevation_mm=3800.0),
            LevelSpec(name="Level2", elevation_mm=7600.0),
            LevelSpec(name="ColumnTop", elevation_mm=12000.0),
            LevelSpec(name="Eave", elevation_mm=12000.0),
            LevelSpec(name="Ridge", elevation_mm=15000.0),
        ],
        grid=GridFrameSpec(
            length_x_mm=60000.0,
            width_y_mm=30000.0,
            bay_spacing_x_mm=6000.0,
            frame_line_y_mm=[0.0, 15000.0, 30000.0],
        ),
        groups=[
            StructuralGroupSpec(
                id="web_members",
                profile_name="RHS90x90x6",
                orientation="truss_web_panels",
                assigned_to_grid="all_frame_lines",
                start_level="Eave",
                end_level="Ridge",
                spacing_mm=2500.0,
                category="beam",
            ),
        ],
    )
    ir = compile_universal_intent_to_ir(intent)
    webs = [element for element in ir.independent_elements if element.id.startswith("web_members")]
    assert len(webs) > 0
    assert max(max(element.start_z, element.end_z) for element in webs) >= 14999.0

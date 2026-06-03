from __future__ import annotations

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.schemas import GridFrameSpec, LevelSpec, StructuralGroupSpec, UniversalStructuralIntent


def test_truss_web_with_duplicate_levels_does_not_emit_zero_segments() -> None:
    intent = UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
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
            StructuralGroupSpec.model_construct(
                id="web_members",
                profile_name="RHS90x90x6",
                orientation="truss_web_panels",
                assigned_to_grid="all_frame_lines",
                start_level="Ridge",
                end_level="Ridge",
                spacing_mm=2500.0,
                category="beam",
            ),
        ],
    )
    ir = compile_universal_intent_to_ir(intent)
    webs = [element for element in ir.independent_elements if element.id.startswith("web_members")]
    assert webs, "truss webs should be generated when Eave/Ridge differ"
    for element in webs:
        length = (
            (element.end_x - element.start_x) ** 2
            + (element.end_y - element.start_y) ** 2
            + (element.end_z - element.start_z) ** 2
        ) ** 0.5
        assert length > 1e-3

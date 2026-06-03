from __future__ import annotations

from pathlib import Path

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.schemas import (
    GridFrameSpec,
    LevelSpec,
    StructuralGroupSpec,
    UniversalStructuralIntent,
)
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent

STEPDOWN_PROMPT = Path(__file__).parent.joinpath("fixtures", "stepdown_facility_prompt.txt").read_text(
    encoding="utf-8"
)

FULL_STEPDOWN = """
Create a highly complex, multi-tiered industrial step-down facility
Total Structural Length (X-Axis): 60000mm
Total Structural Width (Y-Axis): 30000mm
Level 1 (Partial Mezzanine): Z = 3800mm (Spanning from X=0 to X=30000 only)
Level 2 (Suspended Cantilever Deck): Z = 7600mm (Spanning from X=30000 to X=60000, projecting out from Y=0 to Y=10000)
Main Roof Eave Line (Top of Main Columns): Z = 12000mm
Roof Apex / Ridge Line: Z = 15000mm (Centered at Y=15000)
Global Grid Spacing: 6000mm increments along the X-Axis
HEAVY CONCRETE FOUNDATION: IfcSlab Thickness=600mm
DUAL-GRID VERTICAL COLUMNS - 33 Units Total: Profile: HEB450
Grid Line Y=0: 11 columns from X=0 to X=60000 every 6000mm from Z=0 to Z=12000
Grid Line Y=15000 (Mid-Span Spine): 11 columns from X=0 to X=60000 every 6000mm from Z=0 to Z=12000
Grid Line Y=30000: 11 columns from X=0 to X=60000 every 6000mm from Z=0 to Z=12000
Level 1 PARTIAL MEZZANINE FRAME:
Primary Beams: 12 Units of HEB300 at Z_start=3800, Z_end=3800 along grid lines Y=0, Y=15000, and Y=30000
Secondary Floor Joists: 31 Lines of IPE180 along the Y-axis every 1000mm inside X=0 to X=30000
Level 2 SUSPENDED CANTILEVER DECK:
Cantilever Beams: 6 Units of IPE500 from the spine columns (at Y=15000) out to the floating edge (Y=5000) at Z_start=7600
Tension Hanger Rods: 6 Units of CHS89x6 from (Y=15000, Z=12000) to outer floating tips (Y=5000, Z=7600)
Secondary Joists: 16 Lines of IPE140 along the X-axis every 600mm from X=30000 to X=60000
ROOF GABLE TRUSSES:
Top Rafter Chords: Dual-slope IPE300
Bottom Chord Ties: HEA220 at Z_start=12000, Z_end=12000
Web Members: 8 Units per frame of RHS90x90x6 in a Warren truss pattern
ROOF PURLINS: 14 lines of Z250x2.5
Perimeter Wall Girts: 12 lines of C180x2.0
TOTAL X-BRACING SYSTEM:
Vertical Wall Bracing: first bay (X=0 to 6000) and last bay (X=54000 to 60000) CHS76x4 from Z=0 to Z=12000
Roof Plane Bracing: Diagonal X-bracing paths using CHS60x4 connecting the corners of the upper rafter chords in the first, middle, and last bays.
SAFETY GUARDRAILS: RHS50x50x4 at Z=8700
"""


def test_stepdown_structured_parser_matches() -> None:
    intent = parse_structured_prompt_to_universal_intent(FULL_STEPDOWN)
    assert intent is not None
    assert "level1_primary_beams" in {group.id for group in intent.groups}
    assert intent.grid.frame_line_y_mm == [0.0, 15000.0, 30000.0]


def test_stepdown_compiles_without_grid_error() -> None:
    intent = parse_structured_prompt_to_universal_intent(FULL_STEPDOWN)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    assert len(ir.independent_elements) > 150
    assert sum(1 for element in ir.independent_elements if element.category == "slab") == 3
    assert sum(1 for element in ir.independent_elements if "roof_plane_bracing" in element.id) == 6
    assert sum(1 for element in ir.independent_elements if element.id.startswith("level1_primary")) == 12
    assert sum(1 for element in ir.independent_elements if "level2_joists" in element.id) >= 15
    assert sum(1 for element in ir.independent_elements if element.category == "column") == 33


def test_stepdown_fixture_infers_columns_and_warren_webs() -> None:
    intent = parse_structured_prompt_to_universal_intent(STEPDOWN_PROMPT)
    assert intent is not None
    assert intent.grid.frame_line_y_mm == [0.0, 15000.0, 30000.0]
    ir = compile_universal_intent_to_ir(intent)
    assert sum(1 for element in ir.independent_elements if element.category == "column") == 33
    web_count = sum(1 for element in ir.independent_elements if element.id.startswith("web_members"))
    assert web_count == 88


def test_llm_mislabeled_primary_beam_group_is_remapped() -> None:
    intent = UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
            LevelSpec(name="Level1", elevation_mm=3800.0),
        ],
        grid=GridFrameSpec(length_x_mm=30000.0, width_y_mm=30000.0, bay_spacing_x_mm=6000.0),
        groups=[
            StructuralGroupSpec.model_construct(
                id="level1_primary_beams",
                profile_name="HEB300",
                orientation="horizontal_y",
                assigned_to_grid="along_grid_lines_y0_y15000_y30000",
                start_level="Level1",
                end_level="Level1",
                category="beam",
            ),
        ],
    )
    ir = compile_universal_intent_to_ir(intent)
    assert any(element.id.startswith("level1_primary_beams") for element in ir.independent_elements)


def test_extract_pure_stepdown_does_not_raise() -> None:
    intent = parse_structured_prompt_to_universal_intent(FULL_STEPDOWN)
    assert intent is not None
    from analyzer_service.pure_vector_compiler import compile_universal_intent_to_pure_model

    pure = compile_universal_intent_to_pure_model(intent)
    assert len(pure.elements) > 80

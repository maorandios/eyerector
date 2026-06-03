from __future__ import annotations

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.ifc_generator import compile_intent_ir_to_spec_with_constraints
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent

MULTI_STORY_PROMPT = """
Create a massive 3-story industrial facility with a top-level dual-slope truss roof (מבנה תעשייתי 3 קומות עם אגדים ומסבכים)
Total Length (X-Axis): 70000mm (70 meters)
Total Width (Y-Axis): 20000mm (20 meters)
Floor 1 (Ground) Elevation: Z = 0
Floor 2 (Mezzanine 1) Elevation: Z = 4000mm
Floor 3 (Mezzanine 2) Elevation: Z = 8000mm
Roof Eave / Top of Column Elevation: Z = 12000mm (12 meters)
Roof Ridge / Apex Elevation: Z = 14500mm
Bay Spacing: 5000mm increments along the X-Axis (15 structural frames total from X=0 to X=70000)
HEAVY FOUNDATION SLAB (רצפת בטון):
Element Type: IfcSlab
Thickness=500mm
MAIN STRUCTURAL COLUMNS - 30 Units Total:
Profile: HEB400
Place 15 columns along the front line (Y=0) and 15 columns along the back line (Y=20000) spaced every 5000mm.
extrude vertically from the concrete base Z=0 up to the roof line Z=12000.
Floor 2 Framework (Z = 4000):
Primary Beams: Run HEB300 profiles horizontally from column to column along the X-axis and Y-axis at exactly Z_start=4000, Z_end=4000.
Secondary Joists: Run IPE180 profiles across the width (Y-axis) spaced every 2500mm along the X-axis (Z_start=4000, Z_end=4000).
Floor 3 Framework (Z = 8000):
Primary Beams: Run HEB300 profiles horizontally at exactly Z_start=8000, Z_end=8000.
Secondary Joists: Run IPE180 profiles across the width (Y-axis) spaced every 2500mm along the X-axis (Z_start=8000, Z_end=8000).
ROOF GABLE TRUSSES:
Top Chords: Dual-slope IPE270
Bottom Chord: Horizontal UPN240 tie beam at Z_start=12000, Z_end=12000.
Internal Web Members: RHS80x80x5
Roof Purlins: 10 lines of Z200x2.0 running longitudinally along the X-axis
Wall Girts: 8 lines of C150x2.0 on Front Wall (Y=0) and Back Wall (Y=20000)
Wall Bracing: In the first bay (X=0 to X=5000) and last bay (X=65000 to X=70000), place diagonal CHS76x4 cross-braces on the side walls spanning from Z=0 to Z=4000, Z=4000 to Z=8000, and Z=8000 to Z=12000.
"""


def test_multi_story_structured_parser() -> None:
    intent = parse_structured_prompt_to_universal_intent(MULTI_STORY_PROMPT)
    assert intent is not None
    assert any(g.id == "floor2_primary_x" for g in intent.groups)
    assert any(g.id == "floor3_joists" for g in intent.groups)
    columns = next(g for g in intent.groups if g.id == "main_columns")
    assert columns.member_count == 30


def test_multi_story_compiles_without_floor_beam_grid_error() -> None:
    intent = parse_structured_prompt_to_universal_intent(MULTI_STORY_PROMPT)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    assert sum(1 for e in ir.independent_elements if e.category == "column") == 30
    assert sum(1 for e in ir.independent_elements if e.category == "slab") == 1
    assert len(ir.independent_elements) > 200


def test_multi_story_passes_ifc_constraint_compile() -> None:
    intent = parse_structured_prompt_to_universal_intent(MULTI_STORY_PROMPT)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    compile_intent_ir_to_spec_with_constraints(MULTI_STORY_PROMPT, ir)

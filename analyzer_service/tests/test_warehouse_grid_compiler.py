from __future__ import annotations

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.ifc_generator import _parse_prompt_constraints, compile_intent_ir_to_spec_with_constraints
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent

WAREHOUSE_PROMPT = """
Create a massive industrial warehouse with a dual-slope roof supported by complex roof trusses.
Total Length (X-Axis): 80000mm
Total Width (Y-Axis): 20000mm
Eave Height (Z-Axis at side walls): 6000mm
Ridge Height (Z-Axis at apex center): 8500mm
Bay Spacing: 5000mm along the X-Axis
CONCRETE FOUNDATION SLAB - Element Type: IfcSlab
Thickness=400mm
MAIN COLUMNS - Profile: HEB300
ROOF TRUSSES - 17 Truss Assemblies
Top Chords - Profile: IPE270
Bottom Chord - Profile: UPN240
Web Members - Profile: RHS80x80x5
ROOF PURLINS - Profile: Z200x2.0
WALL GIRTS - Profile: C150x2.0
"""


def test_warehouse_structured_intent_parses() -> None:
    intent = parse_structured_prompt_to_universal_intent(WAREHOUSE_PROMPT)
    assert intent is not None
    assert len(intent.slabs) == 1
    assert intent.slabs[0].id == "foundation_slab"
    assert any(g.orientation == "truss_web_panels" for g in intent.groups)


def test_warehouse_compiles_without_slab_group_error() -> None:
    intent = parse_structured_prompt_to_universal_intent(WAREHOUSE_PROMPT)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    assert len(ir.independent_elements) > 100
    assert sum(1 for e in ir.independent_elements if e.category == "slab") == 1
    assert sum(1 for e in ir.independent_elements if e.category == "column") == 34


WAREHOUSE_DUAL_WALL_COLUMNS = WAREHOUSE_PROMPT + """
Place 17 columns along the front wall.
17 matching columns along the back wall.
"""


def test_warehouse_dual_wall_column_count_constraint() -> None:
    constraints = _parse_prompt_constraints(WAREHOUSE_DUAL_WALL_COLUMNS)
    assert constraints.get("count_columns") == 34


def test_warehouse_passes_column_count_validation() -> None:
    intent = parse_structured_prompt_to_universal_intent(WAREHOUSE_PROMPT)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    compile_intent_ir_to_spec_with_constraints(WAREHOUSE_DUAL_WALL_COLUMNS, ir)

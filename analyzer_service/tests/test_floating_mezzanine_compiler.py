from __future__ import annotations

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent

FLOATING_PROMPT = """
Create a suspended, floating industrial mezzanine floor (גלריה מרחפת)
Total Cantilever Length (X-Axis): 50000mm
Total Floating Width/Projection (Y-Axis): 10000mm
Mezzanine Floor Level Elevation: Z = 3500mm
Upper Anchor Level (For Suspension Rods): Z = 7000mm
Bay Spacing: 5000mm
FLOOR SLAB - Element Type: IfcSlab
Thickness=60mm
REAR ANCHOR COLUMNS - 11 Units Total:
Profile: HEB400
11 columns strictly along the back wall line (Y=0)
CANTILEVER PRIMARY BEAMS - 11 Units Total:
Profile: IPE450
FLOOR JOISTS / SECONDARY BEAMS - 26 Lines Total:
Profile: IPE160
every 400mm across the 10000mm floating width
TENSION SUSPENSION RODS - 11 Units Total:
Profile: CHS60x5
FLOOR EDGE GUARDRAIL:
Profile: RHS50x50x4
guardrail lines at Z=4600
"""


def test_floating_mezzanine_parses_all_member_groups() -> None:
    intent = parse_structured_prompt_to_universal_intent(FLOATING_PROMPT)
    assert intent is not None
    group_ids = {group.id for group in intent.groups}
    assert "columns_along_y_min" in group_ids
    assert "beams_along_y_per_x" in group_ids
    assert "joists_along_x_spaced_y" in group_ids
    assert "diagonals_per_x" in group_ids
    assert "edge_at_y_max" in group_ids


def test_floating_mezzanine_compiles_full_model() -> None:
    intent = parse_structured_prompt_to_universal_intent(FLOATING_PROMPT)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    assert sum(1 for e in ir.independent_elements if e.category == "column") == 11
    assert sum(1 for e in ir.independent_elements if e.category == "slab") == 1
    assert len(ir.independent_elements) >= 55

from __future__ import annotations

from analyzer_service.monoslope_shed_builder import build_monoslope_shed_spec, detect_monoslope_prompt


def test_detect_monoslope_prompt() -> None:
    prompt = "Create a monoslope shed with concrete slab and rafters"
    assert detect_monoslope_prompt(prompt)


def test_build_monoslope_member_counts() -> None:
    prompt = """
Create a custom parametric steel monoslope shed with concrete slab.
Total Length: 15000mm
Total Width: 8000mm
Low Side Eave Height: 3500mm
High Side Eave Height: 5000mm
Bay Spacing: 5000mm
COLUMNS SETUP - Profile: HEB200
MONOSLOPE RAFTERS - Profile: IPE300
ROOF PURLINS - Profile: RHS100x100x6
WALL GIRTS - Profile: RHS100x50x4
STRUCTURAL BRACING - Profile: CHS60x4
"""
    spec = build_monoslope_shed_spec(prompt)
    slabs = [e for e in spec.elements if e.type == "slab"]
    columns = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]
    assert len(slabs) == 1
    assert len(columns) == 8
    assert len(beams) == 27


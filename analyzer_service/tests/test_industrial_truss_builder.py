from __future__ import annotations

from analyzer_service.industrial_truss_builder import (
    build_industrial_truss_spec,
    detect_industrial_truss_prompt,
)


def test_detect_industrial_truss_prompt() -> None:
    prompt = "Create a massive industrial warehouse with roof truss and foundation slab"
    assert detect_industrial_truss_prompt(prompt)


def test_build_industrial_truss_counts() -> None:
    prompt = """
Create a massive industrial warehouse with a dual-slope roof supported by complex roof trusses.
Total Length: 10000mm
Total Width: 10000mm
Eave Height: 6000mm
Ridge Height: 8500mm
Bay Spacing: 5000mm
CONCRETE FOUNDATION SLAB - Thickness=400mm
MAIN COLUMNS - Profile: HEB300
Top Chords - Profile: IPE270
Bottom Chord - Profile: UPN240
Web Members - Profile: RHS80x80x5
ROOF PURLINS - Profile: Z200x2.0
WALL GIRTS - Profile: C150x2.0
"""
    spec = build_industrial_truss_spec(prompt)
    slabs = [e for e in spec.elements if e.type == "slab"]
    columns = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]
    # 3 frames -> 6 columns, trusses+webs=30, purlins=12, girts=8 => 50 beams
    assert len(slabs) == 1
    assert len(columns) == 6
    assert len(beams) == 50


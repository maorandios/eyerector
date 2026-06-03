from __future__ import annotations

from analyzer_service.gable_shed_builder import build_dual_slope_gable_spec, detect_dual_slope_gable_prompt


def test_detect_dual_slope_gable_prompt() -> None:
    prompt = "Create a dual-slope gable roof shed with ridge and rafters on columns"
    assert detect_dual_slope_gable_prompt(prompt)


def test_build_dual_slope_gable_spec_member_counts() -> None:
    prompt = """
Create a comprehensive parametric steel shed with a dual-slope gable roof
Total Length: 30000mm
Total Width: 10000mm
Eave Height: 4000mm
Ridge Height: 5500mm
Bay Spacing: 5000mm
COLUMNS SETUP - Profile: HEB200
GABLE ROOF RAFTERS - Profile: IPE300
ROOF PURLINS - Profile: RHS100x100x6
WALL GIRTS - Profile: RHS100x50x4
"""
    spec = build_dual_slope_gable_spec(prompt)
    columns = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]

    assert len(columns) == 14
    assert len(beams) == 28  # 14 rafters + 8 purlins + 6 girts


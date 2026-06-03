from __future__ import annotations

from analyzer_service.llm_extractor import extract_pure_structural_model
from analyzer_service.tests.test_floating_mezzanine_compiler import FLOATING_PROMPT


def test_floating_mezzanine_uses_correct_steel_profiles() -> None:
    model = extract_pure_structural_model(FLOATING_PROMPT)
    profiles = {element.profile_name for element in model.elements}
    assert "HEB400" in profiles
    assert "IPE450" in profiles
    assert "IPE160" in profiles
    assert any(p.upper() == "CHS60X5" for p in profiles)
    assert any(p.upper() == "RHS50X50X4" for p in profiles)
    assert "100x50x4" not in profiles

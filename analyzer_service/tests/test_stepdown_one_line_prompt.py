from __future__ import annotations

from pathlib import Path

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent

ONE_LINE_PROMPT = Path(__file__).parent.joinpath("fixtures", "stepdown_user_exact_prompt.txt").read_text(
    encoding="utf-8"
)


def test_one_line_stepdown_parses_all_tiers() -> None:
    intent = parse_structured_prompt_to_universal_intent(ONE_LINE_PROMPT)
    assert intent is not None
    group_ids = {group.id for group in intent.groups}
    assert "level2_cantilevers" in group_ids
    assert "level2_hangers" in group_ids
    assert "level2_joists" in group_ids
    level1 = next(level for level in intent.levels if level.name == "Level1")
    level2 = next(level for level in intent.levels if level.name == "Level2")
    assert level1.elevation_mm == 3800.0
    assert level2.elevation_mm == 7600.0
    ir = compile_universal_intent_to_ir(intent)
    assert len(ir.independent_elements) >= 290
    assert sum(1 for element in ir.independent_elements if element.id.startswith("level2_")) >= 30

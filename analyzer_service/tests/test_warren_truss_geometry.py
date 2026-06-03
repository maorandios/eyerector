from __future__ import annotations

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent
from analyzer_service.tests.test_stepdown_facility_compiler import FULL_STEPDOWN


def test_warren_web_segments_are_not_flat_at_eave() -> None:
    intent = parse_structured_prompt_to_universal_intent(FULL_STEPDOWN)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    webs = [element for element in ir.independent_elements if element.id.startswith("web_members")]
    assert len(webs) >= 80
    for element in webs:
        length = (
            (element.end_x - element.start_x) ** 2
            + (element.end_y - element.start_y) ** 2
            + (element.end_z - element.start_z) ** 2
        ) ** 0.5
        assert length > 100.0
        if abs(element.start_z - element.end_z) <= 1e-3:
            assert abs(element.start_y - element.end_y) > 500.0

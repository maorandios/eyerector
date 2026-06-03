"""Tests for layout intent normalization."""

from __future__ import annotations

from analyzer_service.intent_normalizer import normalize_layout_intent
from analyzer_service.schemas import ParametricLayoutRequest


def test_prompt_locks_portal_profiles() -> None:
    prompt = "3 columns with a span of 5000mm using IPE300 height 4000mm"
    wrong = ParametricLayoutRequest(
        layout_type="single_element",
        profile_name="HEB200",
        column_count=2,
        total_length_mm=6000.0,
        height_mm=3500.0,
    )
    fixed = normalize_layout_intent(prompt, wrong, [])
    assert fixed.layout_type == "column_row"
    assert fixed.profile_name == "IPE300"
    assert fixed.column_count == 3
    assert fixed.total_length_mm == 5000.0
    assert fixed.height_mm == 4000.0


def test_normalizer_promotes_shed_request() -> None:
    prompt = (
        "create a steel shed length 12000mm width 6000mm height 4000mm "
        "with 6 columns HEB200, rafters IPE300, 4 purlins RHS100x100x6 and base IPE200"
    )
    wrong = ParametricLayoutRequest(
        layout_type="column_row",
        profile_name="HEB200",
        column_count=3,
        total_length_mm=6000.0,
        height_mm=3000.0,
    )
    fixed = normalize_layout_intent(prompt, wrong, [])
    assert fixed.layout_type == "steel_shed"
    assert fixed.total_length_mm == 12000.0
    assert fixed.width_mm == 6000.0
    assert fixed.height_mm == 4000.0

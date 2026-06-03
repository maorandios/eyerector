"""Tests for rule-based layout intent fallback."""

from __future__ import annotations

from analyzer_service.intent_fallback import build_layout_intent_from_context


def test_portal_fallback() -> None:
    prompt = "Beam IPE400 spanning 6000 on 3 columns HEB200 height 3500"
    intent = build_layout_intent_from_context(prompt, [])
    assert intent is not None
    assert intent.layout_type == "portal_frame"
    assert intent.profile_name in ("HEB200", "IPE400")
    assert intent.column_count == 3
    assert intent.height_mm == 3500.0
    assert intent.total_length_mm == 6000.0


def test_portal_fallback_distinct_profiles() -> None:
    prompt = "Beam IPE400 spanning 6000 on 3 columns HEB200 height 3500"
    intent = build_layout_intent_from_context(prompt, [])
    assert intent is not None
    assert intent.resolved_column_profile() == "HEB200"
    assert intent.resolved_beam_profile() == "IPE400"


def test_single_column_fallback() -> None:
    prompt = "HEB240 column height 4 meters"
    intent = build_layout_intent_from_context(prompt, [])
    assert intent is not None
    assert intent.layout_type == "single_element"
    assert intent.profile_name == "HEB240"
    assert intent.height_mm == 4000.0


def test_steel_shed_fallback() -> None:
    prompt = (
        "create a parametric steel shed length 12000mm width 6000mm height 4000mm "
        "6 columns HEB200, main rafters IPE300, 4 purlins RHS100x100x6, base beams IPE200"
    )
    intent = build_layout_intent_from_context(prompt, [])
    assert intent is not None
    assert intent.layout_type == "steel_shed"
    assert intent.total_length_mm == 12000.0
    assert intent.width_mm == 6000.0
    assert intent.height_mm == 4000.0
    assert intent.resolved_column_profile() == "HEB200"
    assert intent.resolved_rafter_profile() == "IPE300"
    assert intent.resolved_purlin_profile() == "100x100x6"
    assert intent.resolved_base_beam_profile() == "IPE200"

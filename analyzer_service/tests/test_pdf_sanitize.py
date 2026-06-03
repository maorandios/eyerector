"""Sanitize AI JSON before PureStructuralModelSpec validation."""

import pytest

from analyzer_service.pdf_validate.sanitize import parse_pure_model_from_llm_json


def test_drops_zero_length_element() -> None:
    raw = """{
        "elements": [
            {"id": "e1", "profile_name": "IPE200", "start_x": 0, "start_y": 0, "start_z": 0,
             "end_x": 5000, "end_y": 0, "end_z": 0},
            {"id": "e2", "profile_name": "IPE200", "start_x": 100, "start_y": 100, "start_z": 0,
             "end_x": 100, "end_y": 100, "end_z": 0}
        ]
    }"""
    model, warnings = parse_pure_model_from_llm_json(raw)
    assert len(model.elements) == 1
    assert model.elements[0].id == "e1"
    assert any("zero-length" in w for w in warnings)

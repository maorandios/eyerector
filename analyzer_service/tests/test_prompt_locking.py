"""Tests that user prompt profile names override LLM mistakes."""

from __future__ import annotations

from analyzer_service.schemas import Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.spec_normalizer import normalize_structural_spec


def test_prompt_locks_beam_ipe_when_llm_sent_heb() -> None:
    prompt = "Beam IPE500 spanning 8000 on 3 columns HEB300 height 4000"
    llm_wrong = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=[200, 200, 9, 15],
                length_mm=3500,
                position=Position3D(x=0),
            ),
            StructuralElement(
                type="beam",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=[200, 200, 9, 15],
                length_mm=6000,
                position=Position3D(z=3500),
            ),
        ]
    )
    fixed = normalize_structural_spec(prompt, llm_wrong, [])
    beam = next(e for e in fixed.elements if e.type == "beam")
    cols = [e for e in fixed.elements if e.type == "column"]
    assert beam.profile_key == "IPE500"
    assert beam.dimensions[0] == 500.0
    assert all(c.profile_key == "HEB300" for c in cols)
    assert beam.length_mm == 8000.0


def test_hebrew_height_metres() -> None:
    prompt = "3 columns HEB240 height 4 meters"
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=[200, 200, 9, 15],
                length_mm=3000,
                position=Position3D(),
            )
        ]
    )
    fixed = normalize_structural_spec(prompt, spec, [])
    assert fixed.elements[0].profile_key == "HEB240"
    assert fixed.elements[0].length_mm == 4000.0

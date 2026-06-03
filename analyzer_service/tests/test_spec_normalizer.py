"""Tests for structural spec normalization and IFC generation."""

from __future__ import annotations

import ifcopenshell

from analyzer_service.ifc_generator import generate_ifc_from_spec
from analyzer_service.schemas import Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.spec_normalizer import (
    build_portal_frame_spec,
    build_rule_fallback_spec,
    normalize_structural_spec,
)


def test_rhs_dimensions_repair_from_prompt() -> None:
    prompt = "RHS200x200x10 column at 0,0 height 3000mm"
    bad = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="RHS",
                dimensions=[100, 100, 10],
                length_mm=3000,
                position=Position3D(),
            )
        ]
    )
    fixed = normalize_structural_spec(prompt, bad)
    assert fixed.elements[0].dimensions == [200.0, 200.0, 10.0]


def test_column_height_from_meters() -> None:
    prompt = "HEB200 column height 4 meters"
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=3000,
                position=Position3D(),
            )
        ]
    )
    fixed = normalize_structural_spec(prompt, spec)
    assert fixed.elements[0].length_mm == 4000.0


def test_portal_frame_three_columns_and_beam() -> None:
    prompt = "Beam IPE400 spanning 6000 mm on 3 columns HEB200 height 3500 at y=0"
    spec = build_portal_frame_spec(prompt)
    assert spec is not None
    columns = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]
    assert len(columns) == 3
    assert len(beams) == 1
    assert [c.position.x for c in columns] == [0.0, 3000.0, 6000.0]
    assert beams[0].position.z == 3500.0
    assert beams[0].length_mm == 6000.0


def test_normalize_fixes_beam_z_on_columns() -> None:
    prompt = "beam on 3 columns HEB200 height 3500 span 6000"
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=3500,
                position=Position3D(x=0),
            ),
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=3500,
                position=Position3D(x=3000),
            ),
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=3500,
                position=Position3D(x=6000),
            ),
            StructuralElement(
                type="beam",
                profile_type="IPE",
                dimensions=[400, 180, 8.6, 13],
                length_mm=6000,
                position=Position3D(z=0),
            ),
        ]
    )
    fixed = normalize_structural_spec(prompt, spec)
    beam = next(e for e in fixed.elements if e.type == "beam")
    assert beam.position.z == 3500.0


def test_normalize_applies_distinct_column_and_beam_profiles() -> None:
    prompt = "Beam IPE500 spanning 8000 on 3 columns HEB300 height 4000"
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=3500,
                position=Position3D(x=0),
            ),
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=3500,
                position=Position3D(x=4000),
            ),
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=3500,
                position=Position3D(x=8000),
            ),
            StructuralElement(
                type="beam",
                profile_type="HEB",
                dimensions=[200, 200, 9, 15],
                length_mm=6000,
                position=Position3D(z=3500),
            ),
        ]
    )
    fixed = normalize_structural_spec(prompt, spec)
    columns = [e for e in fixed.elements if e.type == "column"]
    beam = next(e for e in fixed.elements if e.type == "beam")
    assert all(c.profile_type == "HEB" for c in columns)
    assert columns[0].dimensions[0] == 300.0
    assert beam.profile_type == "IPE"
    assert beam.dimensions[0] == 500.0
    assert beam.length_mm == 8000.0


def test_portal_rebuild_keeps_heb300_not_defaults() -> None:
    prompt = "beam on 2 columns HEB300 height 4000 span 5000"
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                dimensions=[300, 300, 11, 19],
                length_mm=4000,
                position=Position3D(),
            ),
        ]
    )
    fixed = normalize_structural_spec(prompt, spec)
    columns = [e for e in fixed.elements if e.type == "column"]
    assert len(columns) == 2
    assert all(c.dimensions[0] == 300.0 for c in columns)


def test_generate_ifc_portal_frame_product_count() -> None:
    prompt = "Beam IPE400 spanning 6000 on 3 columns HEB200 height 3500"
    spec = build_rule_fallback_spec(prompt)
    assert spec is not None
    data = generate_ifc_from_spec(spec)
    assert len(data) > 1000
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(data)
        model = ifcopenshell.open(path)
        assert len(model.by_type("IfcColumn")) == 3
        assert len(model.by_type("IfcBeam")) == 1
    finally:
        os.unlink(path)

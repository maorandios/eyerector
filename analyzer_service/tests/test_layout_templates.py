"""Tests for parametric layout template compilation."""

from __future__ import annotations

from analyzer_service.layout_templates import compile_layout_to_spec
from analyzer_service.schemas import ParametricLayoutRequest


def test_beam_on_columns_three_bay() -> None:
    request = ParametricLayoutRequest(
        layout_type="portal_frame",
        profile_name="HEB300",
        column_count=3,
        total_length_mm=8000.0,
        height_mm=4000.0,
    )
    spec = compile_layout_to_spec(request)
    columns = sorted([e for e in spec.elements if e.type == "column"], key=lambda c: c.position.x)
    beam = next(e for e in spec.elements if e.type == "beam")

    assert len(columns) == 3
    assert [c.position.x for c in columns] == [0.0, 4000.0, 8000.0]
    assert all(c.profile_key == "HEB300" for c in columns)
    assert beam.profile_key == "HEB300"
    assert beam.position.z == 4000.0
    assert beam.length_mm == 8000.0


def test_column_row_spacing_three_columns_6000_span() -> None:
    request = ParametricLayoutRequest(
        layout_type="column_row",
        profile_name="HEB200",
        column_count=3,
        total_length_mm=6000.0,
        height_mm=3000.0,
    )
    spec = compile_layout_to_spec(request)
    columns = sorted([e for e in spec.elements if e.type == "column"], key=lambda c: c.position.x)

    assert len(columns) == 3
    assert [c.position.x for c in columns] == [0.0, 3000.0, 6000.0]
    assert all(c.position.y == 0.0 for c in columns)
    assert all(c.position.z == 0.0 for c in columns)
    assert all(c.length_mm == 3000.0 for c in columns)


def test_column_row_two_columns_are_exact_endpoints() -> None:
    request = ParametricLayoutRequest(
        layout_type="column_row",
        profile_name="HEB200",
        column_count=2,
        total_length_mm=5000.0,
        height_mm=3500.0,
    )
    spec = compile_layout_to_spec(request)
    columns = sorted([e for e in spec.elements if e.type == "column"], key=lambda c: c.position.x)
    assert [c.position.x for c in columns] == [0.0, 5000.0]


def test_portal_frame_distinct_column_and_beam_profiles() -> None:
    request = ParametricLayoutRequest(
        layout_type="portal_frame",
        profile_name="IPE400",
        column_profile_name="HEB300",
        beam_profile_name="IPE400",
        column_count=2,
        total_length_mm=8000.0,
        height_mm=5000.0,
    )
    spec = compile_layout_to_spec(request)
    columns = [e for e in spec.elements if e.type == "column"]
    beam = next(e for e in spec.elements if e.type == "beam")

    assert all(c.profile_key == "HEB300" for c in columns)
    assert beam.profile_key == "IPE400"


def test_single_column() -> None:
    request = ParametricLayoutRequest(
        layout_type="single_element",
        profile_name="HEB200",
        height_mm=3500.0,
        total_length_mm=3500.0,
    )
    spec = compile_layout_to_spec(request)
    assert len(spec.elements) == 1
    assert spec.elements[0].profile_key == "HEB200"
    assert spec.elements[0].length_mm == 3500.0


def test_steel_shed_compiles_all_member_groups() -> None:
    request = ParametricLayoutRequest(
        layout_type="steel_shed",
        profile_name="IPE300",
        column_profile_name="HEB200",
        rafter_profile_name="IPE300",
        purlin_profile_name="RHS100x100x6",
        base_beam_profile_name="IPE200",
        total_length_mm=12000.0,
        width_mm=6000.0,
        height_mm=4000.0,
        purlin_count=4,
    )
    spec = compile_layout_to_spec(request)
    columns = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]
    rafters = [b for b in beams if b.beam_axis == "Y" and b.position.z == 4000.0 and b.length_mm == 6000.0]
    purlins = [b for b in beams if b.beam_axis == "X" and b.position.z == 4000.0 and b.length_mm == 12000.0]
    base_beams = [b for b in beams if b.position.z == 0.0]

    assert len(columns) == 6
    assert all(c.profile_key == "HEB200" for c in columns)
    assert len(rafters) == 3
    assert all(r.profile_key == "IPE300" for r in rafters)
    assert len(purlins) == 4
    assert all(p.profile_key == "100x100x6" for p in purlins)
    assert len(base_beams) == 4
    assert all(b.profile_key == "IPE200" for b in base_beams)

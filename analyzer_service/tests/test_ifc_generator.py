"""IFC generation tests with catalog-backed profiles."""

from __future__ import annotations

import os
import tempfile

import ifcopenshell
import pytest

from analyzer_service.ifc_generator import IfcGenerationError, generate_ifc_from_spec
from analyzer_service.layout_templates import compile_layout_to_spec
from analyzer_service.schemas import ParametricLayoutRequest, Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.steel_catalog import resolve_profile_key


def _open_generated(spec: StructuralModelSpec) -> ifcopenshell.file:
    data = generate_ifc_from_spec(spec)
    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(data)
        return ifcopenshell.open(path)
    finally:
        os.unlink(path)


def _coords(product) -> tuple[float, float, float]:
    coords = product.ObjectPlacement.RelativePlacement.Location.Coordinates
    return float(coords[0]), float(coords[1]), float(coords[2])


def _extrusion_depth(product) -> float:
    reps = getattr(product.Representation, "Representations", []) or []
    for rep in reps:
        items = getattr(rep, "Items", []) or []
        for item in items:
            depth = getattr(item, "Depth", None)
            if depth is not None:
                return float(depth)
    raise AssertionError(f"No extrusion depth found for product {product.Name}")


def test_ifc_heb200_profile_depth() -> None:
    dims = resolve_profile_key("HEB200").dimensions
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=dims,
                length_mm=3500,
                position=Position3D(),
            )
        ]
    )
    model = _open_generated(spec)
    profiles = model.by_type("IfcIShapeProfileDef")
    assert len(profiles) == 1
    assert float(profiles[0].OverallDepth) == 200.0


def test_ifc_portal_frame_counts() -> None:
    request = ParametricLayoutRequest(
        layout_type="portal_frame",
        profile_name="HEB200",
        column_count=3,
        total_length_mm=6000.0,
        height_mm=3500.0,
    )
    spec = compile_layout_to_spec(request)
    model = _open_generated(spec)
    columns = sorted(model.by_type("IfcColumn"), key=lambda c: _coords(c)[0])
    beams = model.by_type("IfcBeam")

    assert len(columns) == 3
    assert len(beams) == 1

    assert [_coords(c)[0] for c in columns] == [0.0, 3000.0, 6000.0]
    assert all(_coords(c)[1] == 0.0 for c in columns)
    assert all(_coords(c)[2] == 0.0 for c in columns)
    assert all(_extrusion_depth(c) == 3500.0 for c in columns)

    beam = beams[0]
    bx, by, bz = _coords(beam)
    assert (bx, by, bz) == (0.0, 0.0, 3500.0)
    assert _extrusion_depth(beam) == 6000.0


def test_ifc_rhs_wall_thickness() -> None:
    dims = resolve_profile_key("200x200x10").dimensions
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="RHS",
                profile_key="200x200x10",
                dimensions=dims,
                length_mm=3000,
                position=Position3D(),
            )
        ]
    )
    model = _open_generated(spec)
    profiles = model.by_type("IfcRectangleHollowProfileDef")
    assert len(profiles) == 1
    assert float(profiles[0].WallThickness) == 10.0


def _single_column(profile_type: str, profile_key: str) -> StructuralModelSpec:
    dims = resolve_profile_key(profile_key).dimensions
    return StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type=profile_type,
                profile_key=profile_key,
                dimensions=dims,
                length_mm=3000,
                position=Position3D(),
            )
        ]
    )


def test_ifc_upn_channel_profile() -> None:
    model = _open_generated(_single_column("UPN", "UPN200"))
    profiles = model.by_type("IfcUShapeProfileDef")
    assert len(profiles) == 1
    assert float(profiles[0].Depth) == 200.0
    assert float(profiles[0].FlangeWidth) == 75.0
    assert float(profiles[0].WebThickness) == 8.5


def test_ifc_angle_profile() -> None:
    model = _open_generated(_single_column("L", "L100x100x10"))
    profiles = model.by_type("IfcLShapeProfileDef")
    assert len(profiles) == 1
    assert float(profiles[0].Depth) == 100.0
    assert float(profiles[0].Thickness) == 10.0


def test_ifc_chs_profile() -> None:
    model = _open_generated(_single_column("CHS", "CHS168.3x5"))
    profiles = model.by_type("IfcCircleHollowProfileDef")
    assert len(profiles) == 1
    assert float(profiles[0].Radius) == pytest.approx(168.3 / 2.0)
    assert float(profiles[0].WallThickness) == 5.0


def test_ifc_hem_profile() -> None:
    model = _open_generated(_single_column("HEM", "HEM300"))
    profiles = model.by_type("IfcIShapeProfileDef")
    assert len(profiles) == 1
    assert float(profiles[0].OverallDepth) == 340.0


def test_ifc_allows_base_beams_below_column_tops() -> None:
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
    data = generate_ifc_from_spec(spec)
    assert data.startswith(b"ISO-10303-21;")


def test_ifc_allows_sloped_beam_with_direction_vector() -> None:
    col_dims = resolve_profile_key("HEB200").dimensions
    beam_dims = resolve_profile_key("IPE300").dimensions
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=col_dims,
                length_mm=3000,
                position=Position3D(x=0, y=0, z=0),
            ),
            StructuralElement(
                type="column",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=col_dims,
                length_mm=5000,
                position=Position3D(x=6000, y=0, z=0),
            ),
            StructuralElement(
                type="beam",
                profile_type="IPE",
                profile_key="IPE300",
                dimensions=beam_dims,
                length_mm=(6000.0**2 + 2000.0**2) ** 0.5,
                position=Position3D(x=0, y=0, z=3000),
                beam_axis="X",
                beam_direction_vector=[6000.0, 0.0, 2000.0],
            ),
        ]
    )
    model = _open_generated(spec)
    beams = model.by_type("IfcBeam")
    assert len(beams) == 1
    assert _coords(beams[0]) == (0.0, 0.0, 3000.0)
    assert _extrusion_depth(beams[0]) == pytest.approx((6000.0**2 + 2000.0**2) ** 0.5, rel=1e-6)


def test_ifc_raises_when_beam_below_column_top() -> None:
    dims = resolve_profile_key("HEB200").dimensions
    spec = StructuralModelSpec(
        elements=[
            StructuralElement(
                type="column",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=dims,
                length_mm=3500,
                position=Position3D(x=0, y=0, z=0),
            ),
            StructuralElement(
                type="beam",
                profile_type="HEB",
                profile_key="HEB200",
                dimensions=dims,
                length_mm=6000,
                position=Position3D(x=0, y=0, z=2000),  # below top of column (3500)
                beam_axis="X",
            ),
        ]
    )

    with pytest.raises(IfcGenerationError, match="Beam"):
        generate_ifc_from_spec(spec)

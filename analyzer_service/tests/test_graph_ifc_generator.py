from __future__ import annotations

import os
import tempfile

import ifcopenshell
import pytest

from analyzer_service.ifc_generator import IfcGenerationError, generate_ifc_from_graph
from analyzer_service.schemas import DynamicGraphLayoutRequest, IFCElementData, GridPosition


def _open_generated(graph: DynamicGraphLayoutRequest) -> ifcopenshell.file:
    data = generate_ifc_from_graph(graph)
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
    raise AssertionError("No extrusion depth found")


def test_graph_two_pass_columns_and_beams() -> None:
    graph = DynamicGraphLayoutRequest(
        span_x_mm=6000,
        span_y_mm=4000,
        elements=[
            IFCElementData(
                id="col_1",
                type="column",
                profile_name="HEB200",
                height_mm=3500,
                grid_position=GridPosition(row=0, col=0),
            ),
            IFCElementData(
                id="col_2",
                type="column",
                profile_name="HEB200",
                height_mm=3500,
                grid_position=GridPosition(row=0, col=1),
            ),
            IFCElementData(
                id="beam_1",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_1", "col_2"],
            ),
        ],
    )
    model = _open_generated(graph)
    columns = sorted(model.by_type("IfcColumn"), key=lambda c: _coords(c)[0])
    beams = model.by_type("IfcBeam")
    assert len(columns) == 2
    assert len(beams) == 1
    assert _coords(columns[0]) == (0.0, 0.0, 0.0)
    assert _coords(columns[1]) == (6000.0, 0.0, 0.0)
    assert _coords(beams[0]) == (0.0, 0.0, 3500.0)


def test_graph_sloped_beam_uses_true_3d_span_and_start_origin() -> None:
    graph = DynamicGraphLayoutRequest(
        span_x_mm=6000,
        span_y_mm=4000,
        elements=[
            IFCElementData(
                id="col_low",
                type="column",
                profile_name="HEB200",
                height_mm=3000,
                grid_position=GridPosition(row=0, col=0),
            ),
            IFCElementData(
                id="col_high",
                type="column",
                profile_name="HEB200",
                height_mm=5000,
                grid_position=GridPosition(row=0, col=1),
            ),
            IFCElementData(
                id="beam_slope",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_low", "col_high"],
            ),
        ],
    )
    model = _open_generated(graph)
    beam = model.by_type("IfcBeam")[0]
    assert _coords(beam) == (0.0, 0.0, 3000.0)
    assert _extrusion_depth(beam) == pytest.approx((6000.0**2 + 2000.0**2) ** 0.5, rel=1e-6)

    item = beam.Representation.Representations[0].Items[0]
    axis = item.Position.Axis.DirectionRatios
    assert float(axis[0]) == pytest.approx(6000.0 / ((6000.0**2 + 2000.0**2) ** 0.5), rel=1e-6)
    assert float(axis[1]) == pytest.approx(0.0, abs=1e-6)
    assert float(axis[2]) == pytest.approx(2000.0 / ((6000.0**2 + 2000.0**2) ** 0.5), rel=1e-6)


def test_graph_zero_span_beam_is_skipped() -> None:
    graph = DynamicGraphLayoutRequest(
        span_x_mm=6000,
        span_y_mm=4000,
        elements=[
            IFCElementData(
                id="col_1",
                type="column",
                profile_name="HEB200",
                height_mm=3000,
                grid_position=GridPosition(row=0, col=0),
            ),
            IFCElementData(
                id="beam_bad",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_1", "col_1"],
            ),
        ],
    )
    model = _open_generated(graph)
    assert len(model.by_type("IfcBeam")) == 0


def test_graph_unknown_support_beam_is_skipped() -> None:
    graph = DynamicGraphLayoutRequest(
        span_x_mm=6000,
        span_y_mm=4000,
        elements=[
            IFCElementData(
                id="col_1",
                type="column",
                profile_name="HEB200",
                height_mm=3000,
                grid_position=GridPosition(row=0, col=0),
            ),
            IFCElementData(
                id="beam_bad",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_1", "missing_col"],
            ),
        ],
    )
    model = _open_generated(graph)
    assert len(model.by_type("IfcBeam")) == 0


def test_graph_beam_can_be_supported_by_prior_beams() -> None:
    graph = DynamicGraphLayoutRequest(
        span_x_mm=6000,
        span_y_mm=4000,
        elements=[
            IFCElementData(
                id="col_1",
                type="column",
                profile_name="HEB200",
                height_mm=3000,
                grid_position=GridPosition(row=0, col=0),
            ),
            IFCElementData(
                id="col_2",
                type="column",
                profile_name="HEB200",
                height_mm=5000,
                grid_position=GridPosition(row=0, col=1),
            ),
            IFCElementData(
                id="beam_1",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_1", "col_2"],
            ),
            IFCElementData(
                id="beam_2",
                type="beam",
                profile_name="IPE300",
                supported_by=["beam_1", "col_1"],
            ),
        ],
    )
    model = _open_generated(graph)
    assert len(model.by_type("IfcBeam")) == 2


def test_graph_beam_uses_nonzero_pair_from_support_points() -> None:
    graph = DynamicGraphLayoutRequest(
        span_x_mm=5000,
        span_y_mm=5000,
        elements=[
            IFCElementData(
                id="col_a",
                type="column",
                profile_name="HEB200",
                height_mm=4000,
                grid_position=GridPosition(row=0, col=0),
            ),
            IFCElementData(
                id="col_b",
                type="column",
                profile_name="HEB200",
                height_mm=4000,
                grid_position=GridPosition(row=0, col=1),
            ),
            IFCElementData(
                id="col_c",
                type="column",
                profile_name="HEB200",
                height_mm=5500,
                grid_position=GridPosition(row=1, col=0),
            ),
            IFCElementData(
                id="beam_ab",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_a", "col_b"],
            ),
            IFCElementData(
                id="beam_ac",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_a", "col_c"],
            ),
            IFCElementData(
                id="web_member",
                type="beam",
                profile_name="RHS80x80x5",
                supported_by=["beam_ab", "beam_ac", "beam_ab"],
            ),
        ],
    )
    model = _open_generated(graph)
    assert len(model.by_type("IfcBeam")) == 3


def test_graph_single_support_beam_uses_support_member_endpoints() -> None:
    graph = DynamicGraphLayoutRequest(
        span_x_mm=5000,
        span_y_mm=5000,
        elements=[
            IFCElementData(
                id="col_a",
                type="column",
                profile_name="HEB200",
                height_mm=4000,
                grid_position=GridPosition(row=0, col=0),
            ),
            IFCElementData(
                id="col_b",
                type="column",
                profile_name="HEB200",
                height_mm=5500,
                grid_position=GridPosition(row=1, col=0),
            ),
            IFCElementData(
                id="beam_main",
                type="beam",
                profile_name="IPE300",
                supported_by=["col_a", "col_b"],
            ),
            IFCElementData(
                id="beam_sub",
                type="beam",
                profile_name="RHS80x80x5",
                supported_by=["beam_main"],
            ),
        ],
    )
    model = _open_generated(graph)
    assert len(model.by_type("IfcBeam")) == 2


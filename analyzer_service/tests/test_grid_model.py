from __future__ import annotations

from analyzer_service.grid_model import (
    GridAxisModel,
    GridColumnModel,
    GridModel,
    analysis_from_grid_model,
    grid_model_from_payload,
)


def test_analysis_from_grid_model_explicit_placements() -> None:
    model = GridModel(
        crop_width_px=1000,
        crop_height_px=800,
        mm_per_px_x=10.0,
        mm_per_px_y=10.0,
        span_width_mm=10000.0,
        span_height_mm=8000.0,
        axis_x=GridAxisModel(
            lines_px=[0.0, 500.0, 1000.0],
            stations_mm=[0.0, 5000.0, 10000.0],
            bays_mm=[5000.0, 5000.0],
            labels=["1", "2", "3"],
        ),
        axis_y=GridAxisModel(
            lines_px=[800.0, 400.0, 0.0],
            stations_mm=[0.0, 4000.0, 8000.0],
            bays_mm=[4000.0, 4000.0],
            labels=["A", "B", "C"],
        ),
        columns=[
            GridColumnModel(
                id="a",
                mark="C1",
                x_px=0.0,
                y_px=800.0,
                x_mm=0.0,
                y_mm=0.0,
                grid_ix=0,
                grid_iy=0,
            ),
            GridColumnModel(
                id="b",
                mark="C2",
                x_px=500.0,
                y_px=400.0,
                x_mm=5000.0,
                y_mm=4000.0,
                grid_ix=1,
                grid_iy=1,
            ),
        ],
    )
    analysis = analysis_from_grid_model(model, column_profile="HEB200")
    assert len(analysis.column_placements) == 2
    assert analysis.column_placements[0].x_mm == 0.0
    assert analysis.column_placements[1].y_mm == 4000.0
    src = next(p.value for p in analysis.detected_parameters if p.key == "grid_extraction_source")
    assert src == "grid_model_editor"


def test_grid_model_from_payload_clamps_px() -> None:
    payload = {
        "crop_width_px": 500,
        "crop_height_px": 400,
        "mm_per_px_x": 5.0,
        "mm_per_px_y": 5.0,
        "span_width_mm": 2500.0,
        "span_height_mm": 2000.0,
        "axis_x": {
            "lines_px": [0, 250, 500],
            "stations_mm": [0, 1250, 2500],
            "bays_mm": [1250, 1250],
            "labels": ["1", "2", "3"],
        },
        "axis_y": {
            "lines_px": [400, 200, 0],
            "stations_mm": [0, 1000, 2000],
            "bays_mm": [1000, 1000],
            "labels": ["A", "B", "C"],
        },
        "columns": [
            {
                "id": "c1",
                "mark": "C1",
                "x_px": 250,
                "y_px": 200,
                "x_mm": 1250,
                "y_mm": 1000,
                "grid_ix": 1,
                "grid_iy": 1,
                "source": "user",
                "confidence": 1,
            }
        ],
        "notes": [],
        "provenance": {},
    }
    model = grid_model_from_payload(payload)
    assert model.columns[0].x_px == 250.0
    assert model.columns[0].grid_ix == 1

from __future__ import annotations

import pytest

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.region_analysis_schemas import DetectedParameterEntry, RegionStructuralAnalysis


def _params(**kwargs: float | str) -> list[DetectedParameterEntry]:
    return [DetectedParameterEntry(key=k, value=str(v)) for k, v in kwargs.items()]
from analyzer_service.region_intent_mapper import (
    UnsupportedElementError,
    map_region_analysis_to_intent,
)


def test_map_grid_compiles() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        detected_parameters=_params(
            length_x_mm=12000,
            width_y_mm=6000,
            bay_spacing_x_mm=4000,
            eave_height_mm=5000,
            column_profile="HEB200",
            beam_profile="IPE200",
        ),
    )
    intent = map_region_analysis_to_intent(analysis)
    ir = compile_universal_intent_to_ir(intent)
    assert len(ir.independent_elements) > 0
    assert any(e.category == "column" for e in ir.independent_elements)


def test_map_mezzanine_compiles() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="mezzanine",
        confidence=0.85,
        detected_parameters=_params(
            length_x_mm=12000,
            width_y_mm=6000,
            deck_elevation_mm=3200,
            column_bay_spacing_x_mm=4000,
            slab_thickness_mm=50,
        ),
    )
    intent = map_region_analysis_to_intent(analysis)
    ir = compile_universal_intent_to_ir(intent)
    assert any(e.category == "slab" for e in ir.independent_elements)


def test_staircase_raises_unsupported() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="staircase",
        confidence=0.8,
        detected_parameters=_params(flight_width_mm=1200),
    )
    with pytest.raises(UnsupportedElementError):
        map_region_analysis_to_intent(analysis)


def test_grid_6x3_column_layout() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        detected_parameters=_params(
            columns_along_x=6,
            columns_along_y=3,
            bay_spacing_x_mm=8000,
            bay_spacing_y_mm=6000,
        ),
    )
    intent = map_region_analysis_to_intent(analysis)
    assert intent.grid.length_x_mm == 40000.0
    assert intent.grid.width_y_mm == 12000.0
    assert intent.grid.frame_line_y_mm == [0.0, 6000.0, 12000.0]
    ir = compile_universal_intent_to_ir(intent)
    columns = [e for e in ir.independent_elements if e.category == "column"]
    assert len(columns) == 18


def test_parameter_overrides_apply() -> None:
    analysis = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.7,
        detected_parameters=_params(
            length_x_mm=10000, width_y_mm=5000, bay_spacing_x_mm=5000
        ),
    )
    intent = map_region_analysis_to_intent(
        analysis,
        overrides={"length_x_mm": 20000},
    )
    assert intent.grid.length_x_mm == 20000.0

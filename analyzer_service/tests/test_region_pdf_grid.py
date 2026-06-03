from __future__ import annotations

import json
import tempfile
from pathlib import Path

import fitz

from analyzer_service.region_analysis_schemas import (
    ActiveColumnIntersection,
    CropRectNorm,
    DetectedParameterEntry,
    RegionStructuralAnalysis,
)
from analyzer_service.region_pdf_grid import (
    _chain_to_stations,
    _valid_station_chain,
    extract_region_grid_from_pdf,
    merge_pdf_grid_into_analysis,
    parse_crop_rect_norm,
    PdfGridExtraction,
)
from analyzer_service.pdf_project_storage import create_project_from_pdf


def test_chain_to_stations_cumulative() -> None:
    stations, bays = _chain_to_stations([0, 150, 810, 1460, 19050])
    assert stations == [0.0, 150.0, 810.0, 1460.0, 19050.0]
    assert len(bays) == 4


def test_chain_to_stations_from_bays() -> None:
    stations, bays = _chain_to_stations([810, 650, 2810, 3850])
    assert stations[-1] == 810.0 + 650.0 + 2810.0 + 3850.0
    assert len(bays) == 4


def test_valid_station_chain_rejects_noise() -> None:
    good = [0.0, 150.0, 810.0, 1460.0, 19050.0]
    assert _valid_station_chain(good)
    too_many = [float(i * 400) for i in range(40)]
    assert not _valid_station_chain(too_many)


def test_merge_pdf_prefers_vision_when_pdf_has_extra_lines() -> None:
    vision = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        x_grid_positions_mm=[0.0, 150.0, 810.0, 1460.0, 19050.0],
        y_grid_positions_mm=[0.0, 6075.0, 12150.0],
        active_column_intersections=[],
    )
    pdf = PdfGridExtraction(
        x_stations_mm=[float(i * 500) for i in range(15)],
        y_stations_mm=[0.0, 6075.0, 12150.0],
        confidence=0.9,
        source="pdf_hybrid",
    )
    merged = merge_pdf_grid_into_analysis(vision, pdf)
    assert len(merged.x_grid_positions_mm) == 5


def test_merge_pdf_grid_prefers_longer_x() -> None:
    vision = RegionStructuralAnalysis(
        element_type="grid",
        confidence=0.9,
        x_grid_positions_mm=[0.0, 19050.0],
        y_grid_positions_mm=[0.0, 11050.0],
        active_column_intersections=[
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0),
            ActiveColumnIntersection(grid_index_x=1, grid_index_y=0),
        ],
    )
    pdf = PdfGridExtraction(
        x_stations_mm=[0.0, 150.0, 810.0, 1460.0, 19050.0],
        y_stations_mm=[0.0, 200.0, 850.0, 11050.0],
        confidence=0.85,
        source="pdf_hybrid",
    )
    merged = merge_pdf_grid_into_analysis(vision, pdf)
    assert len(merged.x_grid_positions_mm) == 5
    assert len(merged.y_grid_positions_mm) == 4
    assert merged.active_column_intersections[1].grid_index_x == 4


def test_parse_crop_rect_norm() -> None:
    raw = json.dumps({"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.4})
    crop = parse_crop_rect_norm(raw)
    assert crop is not None
    assert crop.w == 0.5


def _dimension_grid_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=2400, height=1800)
    shape = page.new_shape()
    shape.draw_line((200, 1600), (2200, 1600))
    shape.draw_line((200, 200), (200, 1600))
    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()
    page.insert_text((400, 1650), "810", fontsize=10)
    page.insert_text((900, 1650), "650", fontsize=10)
    page.insert_text((1400, 1650), "2810", fontsize=10)
    page.insert_text((2000, 1650), "3850", fontsize=10)
    page.insert_text((200, 400), "6075", fontsize=10)
    page.insert_text((200, 900), "6075", fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_extract_region_grid_from_pdf_project() -> None:
    pdf_bytes = _dimension_grid_pdf()
    with tempfile.TemporaryDirectory() as tmp:
        import os

        os.environ["PDF_PROJECTS_ROOT"] = tmp
        resp = create_project_from_pdf(pdf_bytes, "grid_test.pdf")
        crop = CropRectNorm(x=0.05, y=0.05, w=0.9, h=0.9)
        result = extract_region_grid_from_pdf(
            resp.project_id,
            resp.pages[0].page_index,
            crop,
            scale_note="units mm",
        )
    assert result is not None
    assert result.confidence >= 0.5
    assert len(result.x_stations_mm) >= 3 or len(result.y_stations_mm) >= 2

"""
Prototype: prove vector grid snap is deterministic (no vision / mm guessing).

Run: python -m pytest analyzer_service/tests/test_vector_alignment.py -v
Or:  python -m analyzer_service.tests.test_vector_alignment  (manual block at bottom)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import fitz
import pytest

from analyzer_service.region_analysis_schemas import CropRectNorm
from analyzer_service.vector_grid_extractor import (
    align_columns_to_vector_grid,
    crop_bounds_from_norm,
    extract_vector_grid_from_pdf,
    norm_to_pdf_point,
    UserPin,
    VectorGridExtraction,
)


def test_align_columns_snaps_to_nearest_lines_math() -> None:
    """Pure math: pins between lines snap to closest vector coordinate."""
    grid_x = [100.0, 300.0, 500.0, 700.0]
    grid_y = [80.0, 200.0, 400.0]
    bounds = crop_bounds_from_norm(800.0, 600.0, CropRectNorm(x=0, y=0, w=1, h=1))

    # Pin near x=310 (closer to 300 than 500), y=195 (closer to 200)
    pins = [
        UserPin(id="p1", x_norm=310 / 800, y_norm=195 / 600),
        UserPin(id="p2", x_norm=510 / 800, y_norm=405 / 600),
    ]

    aligned = align_columns_to_vector_grid(pins, grid_x, grid_y, crop_bounds=bounds)

    assert len(aligned) == 2
    assert aligned[0].snapped_x_pt == 300.0
    assert aligned[0].snapped_y_pt == 200.0
    assert aligned[0].grid_index_x == 1
    assert aligned[0].grid_index_y == 1

    assert aligned[1].snapped_x_pt == 500.0
    assert aligned[1].snapped_y_pt == 400.0
    assert aligned[1].grid_index_x == 2
    assert aligned[1].grid_index_y == 2

    # Snapped norm should map back into crop
    assert abs(aligned[0].x_norm - 300 / 800) < 0.001
    assert abs(aligned[0].y_norm - 200 / 600) < 0.001


def test_norm_to_pdf_point_roundtrip() -> None:
    crop = CropRectNorm(x=0.1, y=0.2, w=0.5, h=0.4)
    bounds = crop_bounds_from_norm(1000.0, 800.0, crop)
    x_pt, y_pt = norm_to_pdf_point(0.0, 0.0, bounds)
    assert x_pt == pytest.approx(100.0)
    assert y_pt == pytest.approx(160.0)
    x_pt2, y_pt2 = norm_to_pdf_point(1.0, 1.0, bounds)
    assert x_pt2 == pytest.approx(600.0)
    assert y_pt2 == pytest.approx(480.0)


def _synthetic_grid_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    for x in (100, 300, 500, 700):
        page.draw_line((x, 50), (x, 550))
    for y in (80, 200, 400):
        page.draw_line((50, y), (750, y))
    data = doc.tobytes()
    doc.close()
    return data


def test_extract_vector_grid_from_synthetic_pdf() -> None:
    pdf = _synthetic_grid_pdf()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "grid.pdf"
        path.write_bytes(pdf)
        crop = CropRectNorm(x=0.05, y=0.05, w=0.9, h=0.9)
        result = extract_vector_grid_from_pdf(path, 0, crop)
    assert len(result.grid_lines_x) >= 3
    assert len(result.grid_lines_y) >= 2
    assert result.crop_bounds is not None

    bounds = result.crop_bounds
    pins = [
        UserPin(id="a", x_norm=0.5, y_norm=0.5),
    ]
    aligned = align_columns_to_vector_grid(
        pins,
        result.grid_lines_x,
        result.grid_lines_y,
        crop_bounds=bounds,
    )
    assert len(aligned) == 1
    assert aligned[0].snapped_x_pt in result.grid_lines_x
    assert aligned[0].snapped_y_pt in result.grid_lines_y


def test_end_to_end_manual_grid() -> None:
    """Documented example for manual runs — zero hallucination snap."""
    extraction = VectorGridExtraction(
        grid_lines_x=[0.0, 150.0, 810.0, 1460.0],
        grid_lines_y=[0.0, 6075.0],
        crop_bounds=crop_bounds_from_norm(2000, 1500, CropRectNorm(x=0, y=0, w=1, h=1)),
    )
    # User clicked between 810 and 1460 in x (norm ~0.55)
    pin = UserPin(id="c1", x_norm=0.55, y_norm=0.02)
    out = align_columns_to_vector_grid(
        [pin],
        extraction.grid_lines_x,
        extraction.grid_lines_y,
        crop_bounds=extraction.crop_bounds,
    )
    assert out[0].snapped_x_pt in (810.0, 1460.0)
    assert out[0].snapped_y_pt == 0.0


if __name__ == "__main__":
    test_align_columns_snaps_to_nearest_lines_math()
    test_norm_to_pdf_point_roundtrip()
    test_end_to_end_manual_grid()
    print("vector alignment prototype: OK")

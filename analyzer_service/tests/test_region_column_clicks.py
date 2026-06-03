from __future__ import annotations

from analyzer_service.region_column_clicks import (
    _cluster_axis_px,
    _detect_column_profile_from_page,
    analysis_from_column_clicks,
    ColumnClick,
)
import fitz


def test_cluster_axis_px_merges_close_clicks() -> None:
    xs = _cluster_axis_px([100.0, 105.0, 108.0, 500.0, 502.0], 2000)
    assert len(xs) == 2


def test_analysis_snaps_each_click_to_pdf_grid() -> None:
    clicks = [
        ColumnClick(102.0, 48.0),
        ColumnClick(98.0, 52.0),
        ColumnClick(502.0, 140.0),
    ]
    pdf_xs = [0.0, 150.0, 810.0, 1460.0, 19050.0]
    pdf_ys = [0.0, 6075.0, 12150.0]
    analysis = analysis_from_column_clicks(
        clicks,
        crop_width_px=2000,
        crop_height_px=1500,
        mm_per_px=9.525,
        x_grid_positions_mm=pdf_xs,
        y_grid_positions_mm=pdf_ys,
        column_profile="RHS100X100X5",
    )
    assert len(analysis.column_placements) == 3
    assert analysis.layout_mode == "dense_matrix"
    src = next(p.value for p in analysis.detected_parameters if p.key == "grid_extraction_source")
    assert src == "column_clicks_pdf_grid_snap"
    for col in analysis.column_placements:
        assert col.x_mm in pdf_xs
        assert col.y_mm in pdf_ys


def test_detect_rhs_profile_on_page() -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    page.insert_text((50, 50), "RHS100X100X5", fontsize=10)
    clip = fitz.Rect(0, 0, 600, 400)
    prof = _detect_column_profile_from_page(page, clip)
    doc.close()
    assert prof is not None
    assert "RHS" in prof.upper()

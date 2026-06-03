from __future__ import annotations

from analyzer_service.region_column_clicks import analysis_from_column_clicks, ColumnClick


def test_analysis_snaps_clicks_to_pdf_grid_stations() -> None:
    xs = [0.0, 4000.0, 8000.0, 12000.0]
    ys = [0.0, 6000.0, 12000.0]
    span_x, span_y = 12000.0, 12000.0
    crop_w, crop_h = 1200, 900
    mm_per_px = span_x / crop_w

    # Click near grid line 4000 mm X and 6000 mm Y (bottom-origin)
    x_px = 4000.0 / mm_per_px
    y_px = crop_h - 6000.0 / mm_per_px

    clicks = [
        ColumnClick(
            x_px=x_px + 20,
            y_px=y_px,
            x_norm=(x_px + 20) / crop_w,
            y_norm=y_px / crop_h,
        ),
    ]
    analysis = analysis_from_column_clicks(
        clicks,
        crop_width_px=crop_w,
        crop_height_px=crop_h,
        mm_per_px=mm_per_px,
        span_width_mm=span_x,
        span_height_mm=span_y,
        x_grid_positions_mm=xs,
        y_grid_positions_mm=ys,
    )
    assert len(analysis.column_placements) == 1
    assert analysis.column_placements[0].x_mm == 4000.0
    assert analysis.column_placements[0].y_mm == 6000.0
    src = next(p.value for p in analysis.detected_parameters if p.key == "grid_extraction_source")
    assert src == "column_clicks_pdf_grid_snap"

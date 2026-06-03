from __future__ import annotations

from analyzer_service.vector_grid_extractor import (
    assess_vector_grid_quality,
    CropBoundsPt,
)


def test_rejects_dense_edge_clustered_x_lines() -> None:
    bounds = CropBoundsPt(x0=0.0, y0=0.0, x1=800.0, y1=600.0)
    # Many lines hugging the left crop edge (typical pdfplumber noise)
    xs = [2.0 + i * 1.5 for i in range(40)]
    ys = [100.0, 300.0, 500.0]
    ok, reasons = assess_vector_grid_quality(xs, ys, bounds)
    assert not ok
    assert any("too_many" in r or "edges" in r or "dense" in r for r in reasons)


def test_accepts_evenly_spaced_structural_grid() -> None:
    bounds = CropBoundsPt(x0=0.0, y0=0.0, x1=800.0, y1=600.0)
    xs = [100.0, 300.0, 500.0, 700.0]
    ys = [80.0, 200.0, 400.0]
    ok, reasons = assess_vector_grid_quality(xs, ys, bounds)
    assert ok
    assert not reasons

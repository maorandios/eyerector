from __future__ import annotations

from analyzer_service.region_grid_lines import (
    _clip_lines_to_label_span,
    _snap_labels_to_vectors,
)


def test_snap_labels_to_vectors_uses_nearest_segment() -> None:
    labels = [100.0, 300.0, 500.0]
    vectors = [98.0, 102.0, 295.0, 510.0, 800.0]
    out = _snap_labels_to_vectors(labels, vectors, 1000.0, max_lines=10)
    assert len(out) == 3
    assert abs(out[0] - 98.0) < 5 or abs(out[0] - 102.0) < 5
    assert abs(out[1] - 295.0) < 5
    assert abs(out[2] - 510.0) < 15


def test_clip_lines_drops_border_noise() -> None:
    labels = [200.0, 400.0, 600.0]
    lines = [10.0, 50.0, 210.0, 390.0, 610.0, 900.0]
    out = _clip_lines_to_label_span(lines, labels, 1000.0)
    assert 10.0 not in out
    assert 900.0 not in out
    assert len(out) >= 3

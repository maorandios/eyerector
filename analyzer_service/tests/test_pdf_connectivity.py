"""Connectivity and vision merge helpers."""

from analyzer_service.pdf_validate.connectivity import analyze_model_connectivity
from analyzer_service.pdf_extract.vision import _dedupe_elements, _merge_vision_submodels
from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec
import fitz


def _el(
    el_id: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> PureSteelElementSpec:
    return PureSteelElementSpec(
        id=el_id,
        profile_name="HEB300",
        start_x=x1,
        start_y=y1,
        start_z=0,
        end_x=x2,
        end_y=y2,
        end_z=0,
    )


def test_dedupe_drops_duplicate_segments() -> None:
    elements = [
        _el("a", 0, 0, 6000, 0),
        _el("b", 0, 0, 6000, 0),
        _el("c", 0, 0, 0, 6000),
    ]
    out, dropped = _dedupe_elements(elements, grid_mm=100)
    assert dropped == 1
    assert len(out) == 2


def test_fragmented_model_detected() -> None:
    model = PureStructuralModelSpec(
        elements=[
            _el("left_a", 0, 0, 0, 6000),
            _el("left_b", 0, 0, 6000, 0),
            _el("right", 50000, 0, 56000, 0),
        ],
        slabs=[],
    )
    report = analyze_model_connectivity(model, join_tol_mm=400)
    assert report.is_fragmented
    assert report.cluster_count >= 2


def test_merge_vision_submodels_aligns_quadrant_offset() -> None:
    page = fitz.open()
    try:
        page.new_page(width=1200, height=800)
        p = page[0]
        full = PureStructuralModelSpec(
            elements=[_el("col", 0, 0, 0, 12000)],
            slabs=[],
        )
        quad = PureStructuralModelSpec(
            elements=[_el("beam", 0, 0, 6000, 0)],
            slabs=[],
        )
        clip = fitz.Rect(600, 0, 1200, 400)
        merged, _ = _merge_vision_submodels(
            [("full", full), ("top-right", quad)],
            page=p,
            mm_per_pt=10.0,
            clips={"top-right": clip},
        )
        xs = [e.start_x for e in merged.elements] + [e.end_x for e in merged.elements]
        assert max(xs) > 6000
    finally:
        page.close()

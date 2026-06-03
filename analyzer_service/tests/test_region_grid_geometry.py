from __future__ import annotations

import fitz

from analyzer_service.region_analysis_schemas import ActiveColumnIntersection, CropRectNorm
from analyzer_service.region_grid_geometry import (
    _cluster_coords,
    _expand_lines_for_points,
    _merge_line_positions,
    build_grid_svg,
    extract_region_grid_geometry,
    geometry_from_response,
    geometry_to_response,
    intersections_to_analysis,
    nearest_vertex,
    RegionGridGeometry,
    GridVertex,
)
from analyzer_service.pdf_project_storage import create_project_from_pdf


def _minimal_grid_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    # Vertical grid lines
    for x in (100, 250, 400, 550):
        page.draw_line((x, 80), (x, 520))
    # Horizontal grid lines
    for y in (100, 220, 340, 460):
        page.draw_line((80, y), (620, y))
    page.insert_text((90, 560), "19050", fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_expand_lines_for_points() -> None:
    lines = [0.0, 100.0, 200.0]
    expanded = _expand_lines_for_points(lines, [50.0, 150.0, 199.0], tol_px=8.0)
    assert 50.0 in expanded or any(abs(v - 50) < 8 for v in expanded)
    assert len(expanded) >= 4


def test_merge_line_positions() -> None:
    merged = _merge_line_positions([10.0, 11.0], [105.0, 106.5], tol_px=5.0)
    assert len(merged) == 2
    assert abs(merged[0] - 10.5) < 0.01


def test_cluster_coords() -> None:
    out = _cluster_coords([10.0, 11.0, 50.0, 51.5], tol=5.0)
    assert len(out) == 2
    assert abs(out[0] - 10.5) < 0.01
    assert abs(out[1] - 50.75) < 0.01


def test_build_svg_and_nearest_vertex() -> None:
    geom = RegionGridGeometry(
        crop_width_px=400,
        crop_height_px=300,
        x_lines_px=[100.0, 200.0],
        y_lines_px=[50.0, 150.0],
        vertices=[
            GridVertex(0, 0, 100.0, 50.0),
            GridVertex(1, 0, 200.0, 50.0),
            GridVertex(0, 1, 100.0, 150.0),
            GridVertex(1, 1, 200.0, 150.0),
        ],
        mm_per_px=10.0,
    )
    svg = build_grid_svg(geom)
    assert "<svg" in svg
    assert 'x1="100.00"' in svg
    hit = nearest_vertex(geom, 102.0, 52.0, radius_px=18.0)
    assert hit is not None
    assert hit.grid_index_x == 0 and hit.grid_index_y == 0


def test_intersections_to_analysis_sparse() -> None:
    geom = RegionGridGeometry(
        crop_width_px=400,
        crop_height_px=300,
        x_lines_px=[0.0, 100.0, 200.0],
        y_lines_px=[0.0, 150.0],
        vertices=[],
        mm_per_px=50.0,
    )
    analysis = intersections_to_analysis(
        geom,
        [
            ActiveColumnIntersection(grid_index_x=0, grid_index_y=0, mark="C1"),
            ActiveColumnIntersection(grid_index_x=2, grid_index_y=1, mark="C2"),
        ],
        column_profile="IPE200",
    )
    assert analysis.layout_mode == "sparse_intersections"
    assert len(analysis.active_column_intersections) == 2
    assert analysis.x_grid_positions_mm == [0.0, 5000.0, 10000.0]
    assert analysis.y_grid_positions_mm == [0.0, 7500.0]


def test_extract_region_grid_geometry_from_pdf() -> None:
    pdf = _minimal_grid_pdf()
    with __import__("tempfile").TemporaryDirectory() as tmp:
        import os

        os.environ["PDF_PROJECTS_ROOT"] = tmp
        project = create_project_from_pdf(pdf, "grid-test.pdf")
        crop = CropRectNorm(x=0.05, y=0.05, w=0.9, h=0.9)
        geom = extract_region_grid_geometry(project.project_id, 0, crop)
    assert geom is not None
    assert len(geom.x_lines_px) >= 2
    assert len(geom.y_lines_px) >= 2
    assert len(geom.vertices) == len(geom.x_lines_px) * len(geom.y_lines_px)
    payload = geometry_to_response(geom)
    roundtrip = geometry_from_response(payload)
    assert len(roundtrip.vertices) == len(geom.vertices)

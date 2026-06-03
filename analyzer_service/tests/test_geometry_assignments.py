from __future__ import annotations

from analyzer_service.geometry_assignments import (
    coerce_vertical_assignment,
    normalize_universal_intent_payload,
)
from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.pure_vector_compiler import compile_universal_intent_to_pure_model
from analyzer_service.schemas import (
    GridFrameSpec,
    LevelSpec,
    SlabGroupSpec,
    StructuralGroupSpec,
    UniversalStructuralIntent,
)


def test_coerce_vertical_support_line_assignment() -> None:
    assert coerce_vertical_assignment("along_y_at_support_wall") == "along_all_x_at_y_min"
    assert coerce_vertical_assignment("rear_anchor_line") == "along_all_x_at_y_min"


def test_single_line_columns_compile() -> None:
    intent = UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Ground", elevation_mm=0.0),
            LevelSpec(name="Deck", elevation_mm=3500.0),
            LevelSpec(name="UpperAnchor", elevation_mm=7000.0),
        ],
        grid=GridFrameSpec(length_x_mm=50000.0, width_y_mm=10000.0, bay_spacing_x_mm=5000.0),
        groups=[
            StructuralGroupSpec(
                id="rear_anchor_columns",
                profile_name="HEB400",
                orientation="vertical",
                assigned_to_grid="along_all_x_at_y_min",
                start_level="Ground",
                end_level="UpperAnchor",
                category="column",
            ),
            StructuralGroupSpec(
                id="cantilever_beams",
                profile_name="IPE450",
                orientation="horizontal_y_per_frame",
                assigned_to_grid="along_y_per_frame_line",
                start_level="Deck",
                end_level="Deck",
                category="beam",
            ),
            StructuralGroupSpec(
                id="joists",
                profile_name="IPE160",
                orientation="horizontal_x",
                assigned_to_grid="distributed_along_y",
                start_level="Deck",
                end_level="Deck",
                spacing_mm=400.0,
                category="beam",
            ),
            StructuralGroupSpec(
                id="tension_rods",
                profile_name="CHS60x5",
                orientation="diagonal_plan",
                assigned_to_grid="per_x_station",
                start_level="UpperAnchor",
                end_level="Deck",
                category="brace",
            ),
        ],
        slabs=[SlabGroupSpec(id="deck_slab", top_level="Deck", thickness_mm=60.0)],
    )
    ir = compile_universal_intent_to_ir(intent)
    pure = compile_universal_intent_to_pure_model(intent)
    assert sum(1 for e in ir.independent_elements if e.category == "column") == 11
    assert len(pure.elements) >= 50


def test_normalize_universal_intent_payload_warren_web() -> None:
    payload = normalize_universal_intent_payload(
        {
            "levels": [{"name": "Eave", "elevation_mm": 6000.0}],
            "grid": {"length_x_mm": 1.0, "width_y_mm": 1.0, "bay_spacing_x_mm": 1.0},
            "groups": [
                {
                    "id": "web_members",
                    "profile_name": "RHS80",
                    "orientation": "truss_web_panels",
                    "assigned_to_grid": "warren_web_per_frame",
                    "start_level": "Eave",
                    "end_level": "Ridge",
                    "category": "beam",
                }
            ],
        }
    )
    assert payload["groups"][0]["assigned_to_grid"] == "all_frame_lines"
    assert "warren" in payload["groups"][0]["id"]


def test_warren_web_assignment_normalizes_and_compiles() -> None:
    """LLM/legacy warren_web_per_frame must not fail validation; Warren pattern uses group id."""
    group = StructuralGroupSpec.model_validate(
        {
            "id": "web_members",
            "profile_name": "RHS80x80x5",
            "orientation": "truss_web_panels",
            "assigned_to_grid": "warren_web_per_frame",
            "start_level": "Eave",
            "end_level": "Ridge",
            "member_count": 8,
            "category": "beam",
        }
    )
    assert group.assigned_to_grid == "all_frame_lines"
    assert "warren" in group.id.casefold()

    intent = UniversalStructuralIntent(
        levels=[
            LevelSpec(name="Eave", elevation_mm=6000.0),
            LevelSpec(name="Ridge", elevation_mm=8500.0),
        ],
        grid=GridFrameSpec(length_x_mm=30000.0, width_y_mm=20000.0, bay_spacing_x_mm=5000.0),
        groups=[group],
    )
    ir = compile_universal_intent_to_ir(intent)
    assert any(element.id.startswith("web_members") for element in ir.independent_elements)

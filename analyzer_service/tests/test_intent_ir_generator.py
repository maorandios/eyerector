from __future__ import annotations

import os
import tempfile

import ifcopenshell
import pytest

from analyzer_service.ifc_generator import IfcGenerationError, generate_ifc_from_intent_ir
from analyzer_service.schemas import IndependentElementSpec, StructuralIntentIR


def _base_mezzanine_ir() -> StructuralIntentIR:
    elements: list[IndependentElementSpec] = []
    x_cols = [0.0, 4000.0, 8000.0, 12000.0]
    for i, x in enumerate(x_cols, start=1):
        elements.append(
            IndependentElementSpec(
                id=f"col_front_{i}",
                category="column",
                profile_name="HEB200",
                start_x=x,
                start_y=0.0,
                start_z=0.0,
                end_x=x,
                end_y=0.0,
                end_z=3000.0,
            )
        )
        elements.append(
            IndependentElementSpec(
                id=f"col_back_{i}",
                category="column",
                profile_name="HEB200",
                start_x=x,
                start_y=6000.0,
                start_z=0.0,
                end_x=x,
                end_y=6000.0,
                end_z=3000.0,
            )
        )

    for i in range(1, len(x_cols)):
        xa = x_cols[i - 1]
        xb = x_cols[i]
        elements.append(
            IndependentElementSpec(
                id=f"primary_front_{i}",
                category="beam",
                profile_name="HEB200",
                start_x=xa,
                start_y=0.0,
                start_z=3000.0,
                end_x=xb,
                end_y=0.0,
                end_z=3000.0,
            )
        )
        elements.append(
            IndependentElementSpec(
                id=f"primary_back_{i}",
                category="beam",
                profile_name="HEB200",
                start_x=xa,
                start_y=6000.0,
                start_z=3000.0,
                end_x=xb,
                end_y=6000.0,
                end_z=3000.0,
            )
        )
    elements.append(
        IndependentElementSpec(
            id="primary_cross_1",
            category="beam",
            profile_name="HEB200",
            start_x=0.0,
            start_y=0.0,
            start_z=3000.0,
            end_x=0.0,
            end_y=6000.0,
            end_z=3000.0,
        )
    )
    elements.append(
        IndependentElementSpec(
            id="primary_cross_2",
            category="beam",
            profile_name="HEB200",
            start_x=12000.0,
            start_y=0.0,
            start_z=3000.0,
            end_x=12000.0,
            end_y=6000.0,
            end_z=3000.0,
        )
    )

    for i, x in enumerate([0.0, 2000.0, 4000.0, 6000.0, 8000.0, 10000.0, 12000.0], start=1):
        elements.append(
            IndependentElementSpec(
                id=f"secondary_joist_{i}",
                category="beam",
                profile_name="IPE160",
                start_x=x,
                start_y=0.0,
                start_z=3200.0,
                end_x=x,
                end_y=6000.0,
                end_z=3200.0,
            )
        )

    for i, (sx, sy, ex, ey) in enumerate(
        [
            (0.0, 0.0, 1000.0, 0.0),
            (0.0, 6000.0, 1000.0, 6000.0),
            (12000.0, 0.0, 11000.0, 0.0),
            (12000.0, 6000.0, 11000.0, 6000.0),
        ],
        start=1,
    ):
        elements.append(
            IndependentElementSpec(
                id=f"brace_{i}",
                category="brace",
                profile_name="RHS80x80x5",
                start_x=sx,
                start_y=sy,
                start_z=2200.0,
                end_x=ex,
                end_y=ey,
                end_z=3000.0,
            )
        )

    elements.append(
        IndependentElementSpec(
            id="slab_1",
            category="slab",
            profile_name="CONCRETE_SLAB",
            start_x=0.0,
            start_y=0.0,
            start_z=3150.0,
            end_x=12000.0,
            end_y=6000.0,
            end_z=3200.0,
        )
    )

    return StructuralIntentIR(
        independent_elements=elements,
    )


def _open_ifc_bytes(data: bytes):
    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(data)
        return ifcopenshell.open(path)
    finally:
        os.unlink(path)


def test_generate_ifc_from_intent_ir_does_not_apply_semantic_count_rules() -> None:
    """Pure vector path compiles geometry only; prompt member-class counts are not enforced."""
    prompt = """
Create a heavy-duty industrial mezzanine floor structure.
SUPPORT COLUMNS - 8 Units Total
FLOOR JOISTS - 7 Lines Total
Element Type: IfcSlab
"""
    bad_ir = _base_mezzanine_ir().model_copy(deep=True)
    bad_ir.independent_elements = [
        e for e in bad_ir.independent_elements if not e.id.startswith("secondary_joist_")
    ][:18]

    data = generate_ifc_from_intent_ir(prompt, bad_ir)
    assert len(data) > 0


def test_generate_ifc_from_intent_ir_mezzanine_counts() -> None:
    prompt = """
Create a heavy-duty industrial mezzanine floor structure.
SUPPORT COLUMNS - 8 Units Total
MAIN GIRDERS - 8 Units Total
FLOOR JOISTS - 7 Lines Total
Element Type: IfcSlab
"""
    good_ir = _base_mezzanine_ir()
    data = generate_ifc_from_intent_ir(prompt, good_ir)
    model = _open_ifc_bytes(data)

    assert len(model.by_type("IfcColumn")) == 8
    assert len(model.by_type("IfcSlab")) == 1
    assert len(model.by_type("IfcBeam")) >= 15  # primary + secondary minimum

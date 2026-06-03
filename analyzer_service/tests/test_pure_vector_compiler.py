from __future__ import annotations

import os
import tempfile

import ifcopenshell

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.ifc_generator import compile_pure_to_spec_with_constraints, generate_ifc_from_spec
from analyzer_service.pure_vector_compiler import (
    compile_pure_to_spec,
    compile_universal_intent_to_pure_model,
    ir_to_pure_model,
)
from analyzer_service.schemas import PureSlabBoxSpec, PureSteelElementSpec, PureStructuralModelSpec
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent
from analyzer_service.tests import test_grid_frame_compiler

MEZZANINE_PROMPT = test_grid_frame_compiler.MEZZANINE_PROMPT


def _open_ifc(data: bytes) -> ifcopenshell.file:
    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(data)
        return ifcopenshell.open(path)
    finally:
        os.unlink(path)


def test_pure_steel_segment_compiles_to_beam_and_column() -> None:
    model = PureStructuralModelSpec(
        elements=[
            PureSteelElementSpec(
                id="element_1",
                profile_name="HEB200",
                start_x=0.0,
                start_y=0.0,
                start_z=0.0,
                end_x=0.0,
                end_y=0.0,
                end_z=3000.0,
            ),
            PureSteelElementSpec(
                id="element_2",
                profile_name="IPE200",
                start_x=0.0,
                start_y=0.0,
                start_z=3000.0,
                end_x=4000.0,
                end_y=0.0,
                end_z=3000.0,
            ),
        ]
    )
    spec = compile_pure_to_spec(model)
    types = {e.type for e in spec.elements}
    assert types == {"column", "beam"}


def test_pure_slab_box_compiles() -> None:
    model = PureStructuralModelSpec(
        elements=[
            PureSteelElementSpec(
                id="element_1",
                profile_name="HEB200",
                start_x=0.0,
                start_y=0.0,
                start_z=0.0,
                end_x=0.0,
                end_y=0.0,
                end_z=1000.0,
            ),
        ],
        slabs=[
            PureSlabBoxSpec(
                id="slab_1",
                min_x=0.0,
                min_y=0.0,
                min_z=-500.0,
                max_x=10000.0,
                max_y=5000.0,
                max_z=0.0,
            ),
        ],
    )
    spec = compile_pure_to_spec(model)
    assert any(e.type == "slab" for e in spec.elements)


def test_universal_intent_compiles_to_pure_segments() -> None:
    intent = parse_structured_prompt_to_universal_intent(MEZZANINE_PROMPT)
    assert intent is not None
    pure = compile_universal_intent_to_pure_model(intent)
    ir = compile_universal_intent_to_ir(intent)
    spec, constraints = compile_pure_to_spec_with_constraints(MEZZANINE_PROMPT, pure)
    assert constraints == {}
    assert len(spec.elements) == len(ir.independent_elements)
    data = generate_ifc_from_spec(spec)
    model = _open_ifc(data)
    assert len(model.by_type("IfcColumn")) == 8
    assert len(model.by_type("IfcSlab")) == 1

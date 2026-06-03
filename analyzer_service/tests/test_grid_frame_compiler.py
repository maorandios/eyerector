from __future__ import annotations

import os
import tempfile

import ifcopenshell
import pytest

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.ifc_generator import generate_ifc_from_intent_ir
from analyzer_service.llm_extractor import extract_structural_intent_ir
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent

MEZZANINE_PROMPT = """
Create a heavy-duty industrial mezzanine floor structure.
Mezzanine Total Length (X-Axis): 12000mm
Mezzanine Total Width (Y-Axis): 6000mm
Finished Deck Elevation (Z-Axis Height): 3200mm
Column Bay Spacing: 4000mm along the X-Axis
MEZZANINE FLOOR DECK - Element Type: IfcSlab
Dimensions: Length=12000mm, Width=6000mm, Thickness=50mm
SUPPORT COLUMNS - 8 Units Total
extrude vertically from Z=0 to Z=3000.
MAIN GIRDERS / PRIMARY BEAMS - 8 Units Total
FLOOR JOISTS / SECONDARY BEAMS - 7 Lines Total
Space them evenly every 2000mm along the X-axis
DIAGONAL KNEE BRACES - Add 4 diagonal knee-braces
column body (at Z=2200)
"""


def test_structured_parser_builds_universal_intent() -> None:
    intent = parse_structured_prompt_to_universal_intent(MEZZANINE_PROMPT)
    assert intent is not None
    assert len(intent.groups) >= 4
    assert intent.grid.length_x_mm == 12000.0


def test_grid_compiler_mezzanine_element_count() -> None:
    intent = parse_structured_prompt_to_universal_intent(MEZZANINE_PROMPT)
    assert intent is not None
    ir = compile_universal_intent_to_ir(intent)
    assert len(ir.independent_elements) == 28
    assert sum(1 for e in ir.independent_elements if e.category == "column") == 8
    assert sum(1 for e in ir.independent_elements if e.category == "slab") == 1
    assert sum(1 for e in ir.independent_elements if "floor_joist" in e.id) == 7


def test_extract_structural_intent_ir_via_grid_compiler() -> None:
    ir = extract_structural_intent_ir(MEZZANINE_PROMPT)
    assert len(ir.independent_elements) == 28


def test_mezzanine_ifc_products_via_grid_compiler() -> None:
    ir = extract_structural_intent_ir(MEZZANINE_PROMPT)
    data = generate_ifc_from_intent_ir(MEZZANINE_PROMPT, ir)
    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(data)
        model = ifcopenshell.open(path)
    finally:
        os.unlink(path)

    assert len(model.by_type("IfcColumn")) == 8
    assert len(model.by_type("IfcSlab")) == 1
    assert len(model.by_type("IfcBeam")) == 19

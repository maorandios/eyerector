#!/usr/bin/env python3
"""Diagnose where step-down prompt geometry is lost: parsing vs compile vs IFC."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyzer_service.grid_frame_compiler import compile_universal_intent_to_ir
from analyzer_service.ifc_generator import compile_pure_to_spec_with_constraints, generate_ifc_from_spec
from analyzer_service.llm_extractor import extract_pure_structural_model
from analyzer_service.pure_vector_compiler import compile_universal_intent_to_pure_model
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent

PROMPT_PATH = ROOT / "analyzer_service/tests/fixtures/stepdown_facility_full_prompt.txt"


def main() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    print("=== 1. STRUCTURED PARSER (Python rules, NOT OpenAI) ===")
    intent = parse_structured_prompt_to_universal_intent(prompt)
    if intent is None:
        print("FAIL: parse_structured_prompt_to_universal_intent returned None")
        print("-> Pipeline falls through to OpenAI LLM (simplified generic shed likely)")
    else:
        print("OK: structured intent parsed")
        print("  groups:", [g.id for g in intent.groups])
        print("  slabs:", [s.id for s in intent.slabs])
        print("  levels:", [(l.name, l.elevation_mm) for l in intent.levels])

    print("\n=== 2. GRID COMPILER (Python geometry expansion) ===")
    if intent:
        ir = compile_universal_intent_to_ir(intent)
        tags = (
            "level1_primary",
            "level1_joist",
            "level2_cantilever",
            "level2_hanger",
            "level2_joist",
            "level2_deck",
            "level1_deck",
            "web_members",
            "top_chord",
            "bottom_chord",
            "roof_plane",
            "guard",
        )
        for tag in tags:
            n = sum(1 for e in ir.independent_elements if tag in e.id)
            print(f"  {tag}: {n}")
        print(f"  TOTAL IR elements: {len(ir.independent_elements)}")

    print("\n=== 3. PURE MODEL + IFC (Python render) ===")
    pure = extract_pure_structural_model(prompt)
    print(f"  pure segments: {len(pure.elements)}, slabs: {len(pure.slabs or [])}")
    spec, _ = compile_pure_to_spec_with_constraints(prompt, pure)
    print(f"  StructuralModelSpec elements: {len(spec.elements)}")
    ifc = generate_ifc_from_spec(spec)
    print(f"  IFC bytes: {len(ifc)}")

    source = "generic_sections+geometry" if intent else "llm_intent+geometry"
    print(f"\n=== PIPELINE SOURCE (check X-Eyesteel-Intent header): {source} ===")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Report where PDF → IFC loses geometry (ingest, vision, merge, compile)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyzer_service.pdf_extract.extract import extract_structural_model_from_pdf
from analyzer_service.pdf_ingest.ingest import ingest_pdf_bytes
from analyzer_service.pdf_validate.connectivity import analyze_model_connectivity
from analyzer_service.pure_vector_compiler import compile_pure_to_spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose PDF structural extraction pipeline")
    parser.add_argument("pdf", type=Path, help="Path to structural plan PDF")
    parser.add_argument("--scale", default="units mm", help="Scale note (e.g. units mm)")
    parser.add_argument("--hints", default="page 1", help="Hints (e.g. page 1)")
    args = parser.parse_args()

    data = args.pdf.read_bytes()
    ingest = ingest_pdf_bytes(data)
    print("=== INGEST ===")
    print(f"  pages: {ingest.page_count}")
    print(f"  CAD drawing ops: {ingest.drawing_op_count}")
    print(f"  text chars: {ingest.text_char_count}")
    print(f"  likely_vector: {ingest.likely_vector}")

    result = extract_structural_model_from_pdf(
        data,
        scale_note=args.scale,
        extra_hints=args.hints,
    )
    print("\n=== EXTRACTION ===")
    print(f"  status: {result.status}")
    print(f"  method: {result.extraction_method}")
    print(f"  ai_model: {result.ai_model}")
    print(f"  message: {result.message}")
    for w in result.warnings:
        print(f"  warn: {w}")

    if not result.model:
        print("\nNo model — pipeline stopped before JSON.")
        return 1

    model = result.model
    conn = analyze_model_connectivity(model)
    print("\n=== CONNECTIVITY (after extraction) ===")
    print(f"  {conn.summary()}")
    print(f"  fragmented: {conn.is_fragmented}")

    try:
        spec = compile_pure_to_spec(model)
        print("\n=== IFC COMPILE ===")
        print(f"  structural elements: {len(spec.elements)}")
        cols = sum(1 for e in spec.elements if e.type == "column")
        beams = sum(1 for e in spec.elements if e.type == "beam")
        print(f"  columns: {cols}, beams: {beams}")
    except Exception as exc:
        print(f"\n=== IFC COMPILE FAILED ===\n  {exc}")
        return 1

    print("\n=== WHERE IT FAILS ===")
    if ingest.drawing_op_count > 5000 and len(model.elements) < 30:
        print("  1) VISION/EXTRACTION — dense CAD but very few members (main failure).")
    if conn.is_fragmented:
        print("  2) MERGE/COORDINATES — disconnected clusters (quadrant or invented frames).")
    if conn.span_z_mm < 1000 and len(model.elements) > 5:
        print("  3) Z LEVELS — mostly flat 2D; vision did not read heights.")
    print("  Fix for full building: AI Designer text prompt, not plan PDF vision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

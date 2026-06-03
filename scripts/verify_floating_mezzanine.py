"""Audit floating mezzanine output against prompt requirements."""
from __future__ import annotations

import math
import tempfile
from collections import Counter, defaultdict

import ifcopenshell

from analyzer_service.ifc_generator import compile_pure_to_spec_with_constraints, generate_ifc_from_spec
from analyzer_service.llm_extractor import extract_pure_structural_model
from analyzer_service.tests.test_floating_mezzanine_compiler import FLOATING_PROMPT

FULL_PROMPT = """
Create a suspended, floating industrial mezzanine floor (גלריה מרחפת) with zero ground-support columns, utilizing absolute 3D grid line vectors:
1. GLOBAL PARAMETERS & ELEVATIONS:
- Total Cantilever Length (X-Axis): 50000mm (50 meters)
- Total Floating Width/Projection (Y-Axis): 10000mm (10 meters)
- Main Support Wall / Anchor Line: Located at Y = 0
- Mezzanine Floor Level Elevation: Z = 3500mm
- Upper Anchor Level (For Suspension Rods): Z = 7000mm
- Bay Spacing: 5000mm increments along the X-Axis (11 structural framing lines from X=0 to X=50000)
2. FLOOR SLAB (משטח הגלריה):
- Element Type: IfcSlab - Length=50000mm, Width=10000mm, Thickness=60mm at Z_top=3500
3. REAR ANCHOR COLUMNS (עמודי שדרה אחוריים) - 11 Units Total:
- Profile: HEB400 along Y=0 from Z=0 to Z=7000
4. CANTILEVER PRIMARY BEAMS (קורות זיזיות ראשיות) - 11 Units Total:
- Profile: IPE450 from (X, Y=0, Z=3500) to (X, Y=10000, Z=3500)
5. FLOOR JOISTS / SECONDARY BEAMS (קורות משניות) - 26 Lines Total:
- Profile: IPE160 along X at Z=3500, every 400mm across 10000mm width
6. TENSION SUSPENSION RODS (מוטות תלייה) - 11 Units Total:
- Profile: CHS60x5 from (X, Y=0, Z=7000) to (X, Y=10000, Z=3500)
7. FLOOR EDGE GUARDRAIL (מעקה בטיחות):
- Profile: RHS50x50x4 at Z=4600 on three exposed edges
"""

Z_TOL = 50.0
XY_TOL = 5.0


def _z(seg) -> tuple[float, float]:
    return float(seg.start_z), float(seg.end_z)


def _len(seg) -> float:
    return math.hypot(
        seg.end_x - seg.start_x,
        seg.end_y - seg.start_y,
        seg.end_z - seg.start_z,
    )


def audit_prompt(label: str, prompt: str) -> dict:
    model = extract_pure_structural_model(prompt)
    spec, _ = compile_pure_to_spec_with_constraints(prompt, model)
    data = generate_ifc_from_spec(spec)

    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    ifc = ifcopenshell.open(path)

    segs = model.elements
    vertical = [s for s in segs if abs(s.end_z - s.start_z) / max(_len(s), 1) > 0.95]
    horizontal = [s for s in segs if s not in vertical and _len(s) > 100]
    diagonal = [
        s
        for s in segs
        if s not in vertical
        and abs(s.end_z - s.start_z) / max(_len(s), 1) > 0.1
        and abs(s.end_z - s.start_z) / max(_len(s), 1) < 0.95
    ]

    cols_heb = [s for s in vertical if "HEB400" in s.profile_name.upper() or "HEB" in s.profile_name.upper()]
    cantilever = [
        s
        for s in horizontal
        if abs(s.start_y) < XY_TOL
        and abs(s.end_y - 10000) < XY_TOL
        and abs(s.start_z - 3500) < Z_TOL
    ]
    joists = [
        s
        for s in horizontal
        if abs(s.start_x) < XY_TOL
        and abs(s.end_x - 50000) < XY_TOL
        and 0 < s.start_y < 10000
    ]
    guard = [s for s in horizontal if abs(s.start_z - 4600) < Z_TOL and abs(s.end_z - 4600) < Z_TOL]
    rods = [
        s
        for s in diagonal
        if abs(s.start_y) < XY_TOL
        and abs(s.end_y - 10000) < XY_TOL
        and abs(max(s.start_z, s.end_z) - 7000) < Z_TOL
        and abs(min(s.start_z, s.end_z) - 3500) < Z_TOL
    ]

    y_joist = sorted({round((s.start_y + s.end_y) / 2, 0) for s in joists})
    x_frames = sorted({round(s.start_x, 0) for s in cantilever})

    profiles = Counter(s.profile_name for s in segs)
    slab = model.slabs[0] if model.slabs else None

    return {
        "label": label,
        "segments": len(segs),
        "ifc_columns": len(ifc.by_type("IfcColumn")),
        "ifc_beams": len(ifc.by_type("IfcBeam")),
        "ifc_slabs": len(ifc.by_type("IfcSlab")),
        "intent_header_segments": len(segs),
        "cols_vertical": len(vertical),
        "cols_heb_at_y0": len(cols_heb),
        "col_z_range": (
            (min(min(s.start_z, s.end_z) for s in cols_heb), max(max(s.start_z, s.end_z) for s in cols_heb))
            if cols_heb
            else None
        ),
        "cantilever_ipe": len(cantilever),
        "x_frame_stations": x_frames,
        "joists_along_x": len(joists),
        "joist_y_positions": y_joist,
        "tension_rods": len(rods),
        "guardrail_segments": len(guard),
        "profiles": dict(profiles),
        "slab": (
            {
                "top_z": slab.max_z,
                "thickness": slab.max_z - slab.min_z,
                "length": slab.max_x - slab.min_x,
                "width": slab.max_y - slab.min_y,
            }
            if slab
            else None
        ),
    }


def expected_check(report: dict) -> list[str]:
    issues: list[str] = []
    exp = {
        "segments_min": 60,
        "ifc_columns": 11,
        "ifc_beams_min": 48,
        "ifc_slabs": 1,
        "cols_heb_at_y0": 11,
        "cantilever_ipe": 11,
        "joists_along_x": 26,
        "tension_rods": 11,
        "guardrail_segments": 3,
    }
    for key, want in exp.items():
        val = report.get(key.replace("_min", ""), report.get(key))
        if key.endswith("_min"):
            key = key[:-4]
            val = report.get(key)
            if val is None or val < want:
                issues.append(f"{key}: got {val}, need >={want}")
        elif val != want:
            issues.append(f"{key}: got {val}, need {want}")

    if report["col_z_range"] and (
        report["col_z_range"][0] > Z_TOL or report["col_z_range"][1] < 7000 - Z_TOL
    ):
        issues.append(f"column height: z range {report['col_z_range']}, need ~0–7000")

    if report["slab"]:
        s = report["slab"]
        if abs(s["top_z"] - 3500) > Z_TOL:
            issues.append(f"slab top Z: {s['top_z']}, need 3500")
        if abs(s["thickness"] - 60) > Z_TOL:
            issues.append(f"slab thickness: {s['thickness']}, need 60")
        if abs(s["length"] - 50000) > 100:
            issues.append(f"slab length: {s['length']}, need 50000")
        if abs(s["width"] - 10000) > 100:
            issues.append(f"slab width: {s['width']}, need 10000")

    frames = report["x_frame_stations"]
    if len(frames) != 11:
        issues.append(f"frame lines at X: {len(frames)} stations {frames}, need 11 (0..50000 step 5000)")

    if len(report["joist_y_positions"]) != 26:
        issues.append(
            f"joist Y lines: {len(report['joist_y_positions'])} positions, need 26 (~400mm spacing)"
        )

    return issues


def main() -> None:
    for label, prompt in [("test_fixture", FLOATING_PROMPT), ("full_user_prompt", FULL_PROMPT)]:
        report = audit_prompt(label, prompt)
        issues = expected_check(report)
        print(f"\n=== {label} ===")
        for k, v in report.items():
            if k != "profiles":
                print(f"  {k}: {v}")
        print(f"  profiles: {report['profiles']}")
        if issues:
            print("  ISSUES:")
            for i in issues:
                print(f"    - {i}")
        else:
            print("  OK: matches prompt requirements")


if __name__ == "__main__":
    main()

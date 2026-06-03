from __future__ import annotations

import math
import re

from analyzer_service.catalog_apply import apply_catalog_to_spec
from analyzer_service.schemas import Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.steel_catalog import fallback_profile, normalize_profile_name, resolve_profile_key


def _parse_mm(text: str, pattern: str, default: float) -> float:
    m = re.search(pattern, text, re.IGNORECASE)
    return float(m.group(1)) if m else default


def _profile_after(text: str, section_keyword: str, default_key: str) -> str:
    key_pattern = (
        r"((?:IPE|HEA|HEB|HEM|UPN|UPE)\s*\d{2,4}"
        r"|RHS\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?"
        r"|CHS\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?"
        r"|L\s*\d+[xX×]\d+[xX×]\d+(?:\.\d+)?"
        r"|[CZ]\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?)"
    )
    section = re.search(rf"(?:{section_keyword})[\s\S]{{0,320}}", text, re.IGNORECASE)
    if section:
        m = re.search(rf"Profile\s*:\s*{key_pattern}", section.group(0), re.IGNORECASE)
        if not m:
            m = re.search(key_pattern, section.group(0), re.IGNORECASE)
        if m:
            raw = m.group(1)
            key = normalize_profile_name(raw)
            if key:
                try:
                    resolve_profile_key(key)
                    return key
                except KeyError:
                    pass
            # Simulate C/Z cold-formed with available RHS sections.
            raw_u = raw.strip().upper()
            if raw_u.startswith("Z"):
                return "100x100x6"
            if raw_u.startswith("C"):
                return "100x50x4"
    return default_key


def _beam(profile_key: str, p1: tuple[float, float, float], p2: tuple[float, float, float]) -> StructuralElement:
    sx, sy, sz = p1
    ex, ey, ez = p2
    dx, dy, dz = ex - sx, ey - sy, ez - sz
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 0:
        raise ValueError("Beam endpoints must not be identical")
    resolved = resolve_profile_key(profile_key)
    return StructuralElement(
        type="beam",
        profile_type=resolved.profile_type,
        profile_key=resolved.profile_key,
        dimensions=list(resolved.dimensions),
        length_mm=length,
        beam_axis="X" if abs(dx) >= abs(dy) else "Y",
        beam_direction_vector=[dx / length, dy / length, dz / length],
        position=Position3D(x=sx, y=sy, z=sz),
    )


def detect_industrial_truss_prompt(prompt: str) -> bool:
    lowered = prompt.casefold()
    has_industrial = "industrial warehouse" in lowered or "warehouse" in lowered or "מסבכים" in prompt
    has_truss = "truss" in lowered or "agdi" in lowered or "מסבך" in prompt
    has_slab = "ifcslab" in lowered or "foundation slab" in lowered or "רצפת בטון" in prompt
    return has_industrial and has_truss and has_slab


def _top_z(y: float, width: float, eave_h: float, ridge_h: float) -> float:
    half = width / 2.0
    if y <= half:
        return eave_h + (ridge_h - eave_h) * (y / half)
    return ridge_h - (ridge_h - eave_h) * ((y - half) / half)


def build_industrial_truss_spec(prompt: str) -> StructuralModelSpec:
    length = _parse_mm(prompt, r"Total Length[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 80000.0)
    width = _parse_mm(prompt, r"Total Width[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 20000.0)
    eave_h = _parse_mm(prompt, r"Eave Height[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 6000.0)
    ridge_h = _parse_mm(prompt, r"Ridge Height[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 8500.0)
    bay = _parse_mm(prompt, r"Bay Spacing[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 5000.0)
    slab_t = _parse_mm(prompt, r"Thickness\s*=\s*(\d+(?:\.\d+)?)\s*mm", 400.0)

    col_profile = _profile_after(prompt, r"MAIN COLUMNS|עמודים ראשיים", "HEB300")
    top_chord_profile = _profile_after(prompt, r"Top Chords|חגורה עליונה", "IPE270")
    bottom_chord_profile = _profile_after(prompt, r"Bottom Chord|חגורה תחתונה", "UPN240")
    web_profile = _profile_after(prompt, r"Web Members|פנימיים למסבך", "80x80x5")
    roof_purlin_profile = _profile_after(prompt, r"ROOF PURLINS|מרישי גג", "100x100x6")
    wall_girt_profile = _profile_after(prompt, r"WALL GIRTS|מרישי קיר", "100x50x4")

    x_lines = [float(i) for i in range(0, int(length) + 1, int(bay))]
    if x_lines[-1] != length:
        x_lines.append(length)

    elements: list[StructuralElement] = []

    # Foundation slab centered; top at Z=0.
    elements.append(
        StructuralElement(
            type="slab",
            profile_type="RHS",
            profile_key="CONCRETE_SLAB",
            dimensions=[length, width, slab_t],
            length_mm=slab_t,
            position=Position3D(x=length / 2.0, y=width / 2.0, z=0.0),
        )
    )

    col_resolved = resolve_profile_key(col_profile)
    # 34 main columns.
    for x in x_lines:
        for y in (0.0, width):
            elements.append(
                StructuralElement(
                    type="column",
                    profile_type=col_resolved.profile_type,
                    profile_key=col_resolved.profile_key,
                    dimensions=list(col_resolved.dimensions),
                    length_mm=eave_h,
                    position=Position3D(x=x, y=y, z=0.0),
                )
            )

    # Truss assemblies per frame line.
    y_nodes = [float(i) for i in range(0, int(width) + 1, 2500)]
    for x in x_lines:
        # Top chords.
        elements.append(_beam(top_chord_profile, (x, 0.0, eave_h), (x, width / 2.0, ridge_h)))
        elements.append(_beam(top_chord_profile, (x, width / 2.0, ridge_h), (x, width, eave_h)))
        # Bottom chord.
        elements.append(_beam(bottom_chord_profile, (x, 0.0, eave_h), (x, width, eave_h)))

        # Web verticals.
        for y in y_nodes[1:-1]:
            elements.append(_beam(web_profile, (x, y, eave_h), (x, y, _top_z(y, width, eave_h, ridge_h))))
        # Web diagonals (alternating per panel).
        for i in range(len(y_nodes) - 1):
            y0, y1 = y_nodes[i], y_nodes[i + 1]
            if i % 2 == 0:
                elements.append(_beam(web_profile, (x, y0, eave_h), (x, y1, _top_z(y1, width, eave_h, ridge_h))))
            else:
                elements.append(_beam(web_profile, (x, y1, eave_h), (x, y0, _top_z(y0, width, eave_h, ridge_h))))

    # Roof purlins: 6 lines each slope (12 total) along X.
    for i in range(1, 7):
        y_left = (width / 2.0) * (i / 7.0)
        z_left = _top_z(y_left, width, eave_h, ridge_h)
        elements.append(_beam(roof_purlin_profile, (0.0, y_left, z_left), (length, y_left, z_left)))

        y_right = width / 2.0 + (width / 2.0) * (i / 7.0)
        z_right = _top_z(y_right, width, eave_h, ridge_h)
        elements.append(_beam(roof_purlin_profile, (0.0, y_right, z_right), (length, y_right, z_right)))

    # Wall girts: 4 lines both side walls.
    for z in (1500.0, 3000.0, 4500.0, 5800.0):
        elements.append(_beam(wall_girt_profile, (0.0, 0.0, z), (length, 0.0, z)))
        elements.append(_beam(wall_girt_profile, (0.0, width, z), (length, width, z)))

    return apply_catalog_to_spec(StructuralModelSpec(elements=elements))


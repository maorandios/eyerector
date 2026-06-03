from __future__ import annotations

import math
import re

from analyzer_service.catalog_apply import apply_catalog_to_spec
from analyzer_service.schemas import Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.steel_catalog import fallback_profile, normalize_profile_name, resolve_profile_key


def _parse_mm(text: str, pattern: str, default: float) -> float:
    m = re.search(pattern, text, re.IGNORECASE)
    return float(m.group(1)) if m else default


def _profile_after(text: str, section_keyword: str, default_family: str) -> str:
    key_pattern = (
        r"((?:IPE|HEA|HEB|HEM|UPN|UPE)\s*\d{2,4}"
        r"|RHS\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?"
        r"|CHS\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?"
        r"|L\s*\d+[xX×]\d+[xX×]\d+(?:\.\d+)?)"
    )
    section = re.search(rf"(?:{section_keyword})[\s\S]{{0,280}}", text, re.IGNORECASE)
    if section:
        m = re.search(rf"Profile\s*:\s*{key_pattern}", section.group(0), re.IGNORECASE)
        if not m:
            m = re.search(key_pattern, section.group(0), re.IGNORECASE)
        if m:
            key = normalize_profile_name(m.group(1))
            if key:
                return key
    return fallback_profile(default_family).profile_key


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


def detect_monoslope_prompt(prompt: str) -> bool:
    lowered = prompt.casefold()
    has_mono = "monoslope" in lowered or "חד-שיפוע" in prompt or "שיפוע אחד" in prompt
    has_slab = "ifcslab" in lowered or "concrete slab" in lowered or "רצפת בטון" in prompt
    has_rafters = "rafter" in lowered or "קורות גג" in prompt
    return has_mono and has_slab and has_rafters


def _parse_height_list(text: str, section_keyword: str, default_values: list[float]) -> list[float]:
    section = re.search(rf"(?:{section_keyword})[\s\S]{{0,260}}", text, re.IGNORECASE)
    if not section:
        return default_values
    m = re.search(r"Z\s*=\s*([0-9,\s]+)", section.group(0), re.IGNORECASE)
    if not m:
        return default_values
    raw_values = [float(v.strip()) for v in m.group(1).split(",") if v.strip().isdigit()]
    return raw_values if raw_values else default_values


def _sanitize_back_girts(values: list[float], high_eave: float) -> list[float]:
    out: list[float] = []
    for v in values:
        vv = v
        if vv > high_eave * 1.5:
            vv = vv / 10.0
        vv = max(200.0, min(vv, high_eave - 200.0))
        out.append(vv)
    return out


def build_monoslope_shed_spec(prompt: str) -> StructuralModelSpec:
    length = _parse_mm(prompt, r"Total Length[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 15000.0)
    width = _parse_mm(prompt, r"Total Width[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 8000.0)
    low_h = _parse_mm(prompt, r"Low Side Eave Height[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 3500.0)
    high_h = _parse_mm(prompt, r"High Side Eave Height[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 5000.0)
    bay = _parse_mm(prompt, r"Bay Spacing[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 5000.0)
    slab_t = _parse_mm(prompt, r"Thickness\s*=\s*(\d+(?:\.\d+)?)\s*mm", 400.0)

    col_profile = _profile_after(prompt, r"COLUMNS SETUP|עמודי", "HEB")
    rafter_profile = _profile_after(prompt, r"MONOSLOPE RAFTERS|קורות גג", "IPE")
    roof_purlin_profile = _profile_after(prompt, r"ROOF\s*&\s*WALL PURLINS|Roof Purlins", "RHS")
    wall_girt_profile = _profile_after(prompt, r"WALL GIRTS|Wall Girts|מרישי קיר", "RHS")
    brace_profile = _profile_after(prompt, r"STRUCTURAL BRACING|קושרות", "CHS")

    x_lines = [float(i) for i in range(0, int(length) + 1, int(bay))]
    if x_lines[-1] != length:
        x_lines.append(length)

    elements: list[StructuralElement] = []

    # Concrete slab top at Z=0, extruded downward.
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
    # 8 columns (front low, back high).
    for x in x_lines:
        elements.append(
            StructuralElement(
                type="column",
                profile_type=col_resolved.profile_type,
                profile_key=col_resolved.profile_key,
                dimensions=list(col_resolved.dimensions),
                length_mm=low_h,
                position=Position3D(x=x, y=0.0, z=0.0),
            )
        )
        elements.append(
            StructuralElement(
                type="column",
                profile_type=col_resolved.profile_type,
                profile_key=col_resolved.profile_key,
                dimensions=list(col_resolved.dimensions),
                length_mm=high_h,
                position=Position3D(x=x, y=width, z=0.0),
            )
        )

    # 4 sloped rafters.
    for x in x_lines:
        elements.append(_beam(rafter_profile, (x, 0.0, low_h), (x, width, high_h)))

    # Roof purlins: 5 lines along X spaced on roof slope.
    for i in range(1, 6):
        y = width * (i / 6.0)
        z = low_h + (high_h - low_h) * (y / width)
        elements.append(_beam(roof_purlin_profile, (0.0, y, z), (length, y, z)))

    # Wall girts: 3 lines each side along X.
    front_zs = _parse_height_list(prompt, r"Front Wall", [1000.0, 2000.0, 3000.0])[:3]
    back_zs_raw = _parse_height_list(prompt, r"Back Wall", [1200.0, 2400.0, 3600.0])[:3]
    back_zs = _sanitize_back_girts(back_zs_raw, high_h)
    for z in front_zs:
        elements.append(_beam(wall_girt_profile, (0.0, 0.0, z), (length, 0.0, z)))
    for z in back_zs:
        elements.append(_beam(wall_girt_profile, (0.0, width, z), (length, width, z)))

    # Wall X-bracing in first and last bay, both walls.
    wall_bays = [(x_lines[0], x_lines[1]), (x_lines[-2], x_lines[-1])]
    for xa, xb in wall_bays:
        # front wall
        elements.append(_beam(brace_profile, (xa, 0.0, 0.0), (xb, 0.0, low_h)))
        elements.append(_beam(brace_profile, (xb, 0.0, 0.0), (xa, 0.0, low_h)))
        # back wall
        elements.append(_beam(brace_profile, (xa, width, 0.0), (xb, width, high_h)))
        elements.append(_beam(brace_profile, (xb, width, 0.0), (xa, width, high_h)))

    # Roof X-bracing in first and last bay.
    for xa, xb in wall_bays:
        elements.append(_beam(brace_profile, (xa, 0.0, low_h), (xb, width, high_h)))
        elements.append(_beam(brace_profile, (xb, 0.0, low_h), (xa, width, high_h)))

    return apply_catalog_to_spec(StructuralModelSpec(elements=elements))


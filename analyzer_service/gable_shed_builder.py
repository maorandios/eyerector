from __future__ import annotations

import math
import re

from analyzer_service.catalog_apply import apply_catalog_to_spec
from analyzer_service.schemas import Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.steel_catalog import fallback_profile, normalize_profile_name, resolve_profile_key


def _parse_mm(text: str, label_pattern: str, default: float) -> float:
    m = re.search(label_pattern, text, re.IGNORECASE)
    if not m:
        return default
    return float(m.group(1))


def _profile_after(text: str, section_keyword: str, default_family: str) -> str:
    key_pattern = (
        r"((?:IPE|HEA|HEB|HEM|UPN|UPE)\s*\d{2,4}"
        r"|RHS\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?)"
    )
    section = re.search(rf"(?:{section_keyword})[\s\S]{{0,220}}", text, re.IGNORECASE)
    if section:
        m = re.search(rf"Profile\s*:\s*{key_pattern}", section.group(0), re.IGNORECASE)
        if not m:
            m = re.search(key_pattern, section.group(0), re.IGNORECASE)
        if m:
            raw = m.group(1)
            key = normalize_profile_name(raw)
            if key:
                return key
    return fallback_profile(default_family).profile_key


def _beam_from_endpoints(profile_key: str, start: tuple[float, float, float], end: tuple[float, float, float]) -> StructuralElement:
    sx, sy, sz = start
    ex, ey, ez = end
    dx, dy, dz = ex - sx, ey - sy, ez - sz
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 0:
        raise ValueError("Beam endpoints must not be identical")
    dir_vector = [dx / length, dy / length, dz / length]
    resolved = resolve_profile_key(profile_key)
    return StructuralElement(
        type="beam",
        profile_type=resolved.profile_type,
        profile_key=resolved.profile_key,
        dimensions=list(resolved.dimensions),
        length_mm=length,
        beam_axis="X" if abs(dx) >= abs(dy) else "Y",
        beam_direction_vector=dir_vector,
        position=Position3D(x=sx, y=sy, z=sz),
    )


def detect_dual_slope_gable_prompt(prompt: str) -> bool:
    lowered = prompt.casefold()
    has_gable = "gable" in lowered or "דו-שיפוע" in prompt
    has_ridge = "ridge" in lowered or "apex" in lowered or "רכס" in prompt
    has_columns = "column" in lowered or "עמוד" in prompt
    has_rafters = "rafter" in lowered or "קורות גג" in prompt
    return has_gable and has_ridge and has_columns and has_rafters


def build_dual_slope_gable_spec(prompt: str) -> StructuralModelSpec:
    length = _parse_mm(prompt, r"Total Length[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 30000.0)
    width = _parse_mm(prompt, r"Total Width[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 10000.0)
    eave_h = _parse_mm(prompt, r"(?:Eave Height|Side Wall Height)[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 4000.0)
    ridge_h = _parse_mm(prompt, r"(?:Ridge Height|Roof Apex)[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 5500.0)
    bay = _parse_mm(prompt, r"Bay Spacing[^\n\r]*?:\s*(\d+(?:\.\d+)?)\s*mm", 5000.0)

    col_profile = _profile_after(prompt, r"COLUMNS SETUP|עמודי", "HEB")
    rafter_profile = _profile_after(prompt, r"GABLE ROOF RAFTERS|קורות גג", "IPE")
    purlin_profile = _profile_after(prompt, r"ROOF PURLINS|מרישי גג|פטות", "RHS")
    girt_profile = _profile_after(prompt, r"WALL GIRTS|מרישי קיר", "RHS")

    x_lines = [float(i) for i in range(0, int(length) + 1, int(bay))]
    if x_lines[-1] != length:
        x_lines.append(length)
    ridge_y = width / 2.0

    elements: list[StructuralElement] = []

    # 14 side columns.
    col_resolved = resolve_profile_key(col_profile)
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

    # 14 rafters (2 per frame line) to ridge node.
    for x in x_lines:
        front_top = (x, 0.0, eave_h)
        ridge = (x, ridge_y, ridge_h)
        back_top = (x, width, eave_h)
        elements.append(_beam_from_endpoints(rafter_profile, front_top, ridge))
        elements.append(_beam_from_endpoints(rafter_profile, ridge, back_top))

    # 8 roof purlins along X, 4 on each slope.
    for i in range(1, 5):
        # left slope
        y_left = ridge_y * (i / 5.0)
        z_left = eave_h + (ridge_h - eave_h) * (y_left / ridge_y)
        elements.append(_beam_from_endpoints(purlin_profile, (0.0, y_left, z_left), (length, y_left, z_left)))
        # right slope
        y_right = ridge_y + ridge_y * (i / 5.0)
        z_right = ridge_h - (ridge_h - eave_h) * (i / 5.0)
        elements.append(_beam_from_endpoints(purlin_profile, (0.0, y_right, z_right), (length, y_right, z_right)))

    # 6 wall girts along X.
    for z in (1000.0, 2000.0, 3000.0):
        elements.append(_beam_from_endpoints(girt_profile, (0.0, 0.0, z), (length, 0.0, z)))
        elements.append(_beam_from_endpoints(girt_profile, (0.0, width, z), (length, width, z)))

    return apply_catalog_to_spec(StructuralModelSpec(elements=elements))


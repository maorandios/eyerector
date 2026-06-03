"""
Post-LLM repair and deterministic structural parsing for chat-to-IFC.

Single source of truth for regex profile/length parsing and portal-frame assembly.
"""

from __future__ import annotations

import re
from typing import Literal

from analyzer_service.catalog_apply import apply_catalog_to_spec
from analyzer_service.schemas import HistoryMessage, Position3D, StructuralElement, StructuralModelSpec
from analyzer_service.steel_catalog import (
    fallback_profile,
    resolve_from_text,
    resolve_from_text_for_role,
    resolve_profile_key,
)

ProfileFamily = Literal["RHS", "HEA", "HEB", "IPE"]

Z_EPS_MM = 0.5
DIM_REL_TOLERANCE = 0.05


def parse_rhs_dimensions(prompt: str) -> list[float] | None:
    patterns = (
        r"RHS\s*(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)",
        r"RHS\s*(\d+)\s*[/]\s*(\d+)\s*[/]\s*(\d+)",
        r"\b(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)\s*(?:mm|מ[\"']?מ)?\b",
    )
    for pattern in patterns:
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            return [float(m.group(1)), float(m.group(2)), float(m.group(3))]
    return None


def _catalog_i_dims(family: str, size: int) -> list[float]:
    key = f"{family.upper()}{size}"
    try:
        return list(resolve_profile_key(key).dimensions)
    except KeyError:
        return list(fallback_profile(family).dimensions)


def parse_i_profile(prompt: str) -> tuple[ProfileFamily, list[float], str] | None:
    key = resolve_from_text(prompt)
    if key and key[:3] in ("HEB", "HEA", "IPE"):
        resolved = resolve_profile_key(key)
        return resolved.profile_type, list(resolved.dimensions), resolved.profile_key  # type: ignore[return-value]
    m = re.search(r"\b(HEB|HEA|IPE)\s*(\d{2,3})\b", prompt, re.IGNORECASE)
    if not m:
        return None
    family = m.group(1).upper()
    prof_key = f"{family}{m.group(2)}"
    return family, _catalog_i_dims(m.group(1), int(m.group(2))), prof_key  # type: ignore[return-value]


def _role_keyword_positions(prompt: str, role: Literal["column", "beam"]) -> list[int]:
    if role == "column":
        pattern = r"\b(?:column|columns|עמוד|עמודים)\b"
    else:
        pattern = r"\b(?:beam|beams|קורה|קורות)\b"
    return [m.start() for m in re.finditer(pattern, prompt, re.IGNORECASE)]


def parse_i_profile_for_role(
    prompt: str, role: Literal["column", "beam"]
) -> tuple[ProfileFamily, list[float], str] | None:
    """
    Match I-section size to column vs beam wording.

    When multiple profiles appear (e.g. IPE500 beam + HEB300 columns), pick the token
    that is closest to this role's keywords and not closer to the other role's keywords.
    """
    key = resolve_from_text_for_role(prompt, role)
    if key and key[:3] in ("HEB", "HEA", "IPE"):
        resolved = resolve_profile_key(key)
        return resolved.profile_type, list(resolved.dimensions), resolved.profile_key  # type: ignore[return-value]

    prof_re = re.compile(r"\b(HEB|HEA|IPE)\s*(\d{2,3})\b", re.IGNORECASE)
    profiles = list(prof_re.finditer(prompt))
    if not profiles:
        return None

    role_anchors = _role_keyword_positions(prompt, role)
    other_role: Literal["column", "beam"] = "beam" if role == "column" else "column"
    other_anchors = _role_keyword_positions(prompt, other_role)

    if not role_anchors:
        return None

    def distance(pos: int, anchors: list[int]) -> float:
        if not anchors:
            return float("inf")
        return float(min(abs(pos - a) for a in anchors))

    best_match: re.Match[str] | None = None
    best_score = float("inf")
    for m in profiles:
        pos = m.start()
        d_role = distance(pos, role_anchors)
        d_other = distance(pos, other_anchors)
        if d_other < d_role:
            continue
        if d_role < best_score:
            best_score = d_role
            best_match = m

    if best_match is None:
        key = resolve_from_text_for_role(prompt, role)
        if key:
            resolved = resolve_profile_key(key)
            return resolved.profile_type, list(resolved.dimensions), resolved.profile_key  # type: ignore[return-value]
        return None
    family = best_match.group(1).upper()
    prof_key = f"{family}{best_match.group(2)}"
    return family, _catalog_i_dims(best_match.group(1), int(best_match.group(2))), prof_key  # type: ignore[return-value]


def combined_prompt_for_parsing(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> str:
    """Merge recent user turns so profiles stated earlier are not lost."""
    parts: list[str] = []
    if history:
        for msg in history[-8:]:
            if msg.role == "user" and msg.text.strip():
                parts.append(msg.text.strip())
    if prompt.strip():
        parts.append(prompt.strip())
    return "\n".join(parts) if parts else prompt


def _profile_from_prompt_for_element(
    text: str,
    element: StructuralElement,
) -> tuple[ProfileFamily, list[float], str | None] | None:
    role: Literal["column", "beam"] = "column" if element.type == "column" else "beam"
    i_prof = parse_i_profile_for_role(text, role)
    if i_prof is not None:
        return i_prof
    if parse_i_profile(text) is not None:
        columns = "column" in text.casefold() or "עמוד" in text
        beams = "beam" in text.casefold() or "קורה" in text
        only_columns = columns and not beams and element.type == "column"
        only_beams = beams and not columns and element.type == "beam"
        if only_columns or only_beams:
            return parse_i_profile(text)
    rhs = parse_rhs_dimensions(text)
    if rhs is not None:
        w, h, t = int(rhs[0]), int(rhs[1]), int(rhs[2])
        return "RHS", rhs, f"{w}x{h}x{t}"
    return None


def parse_position(prompt: str) -> Position3D:
    at = re.search(
        r"(?:at|@|position|מיקום)\s*[\(\[]?\s*(\d+(?:\.\d+)?)\s*[,;\s]\s*(\d+(?:\.\d+)?)"
        r"(?:\s*[,;\s]\s*(\d+(?:\.\d+)?))?\s*[\)\]]?",
        prompt,
        re.IGNORECASE,
    )
    if at:
        return Position3D(
            x=float(at.group(1)),
            y=float(at.group(2)),
            z=float(at.group(3)) if at.group(3) else 0.0,
        )
    y_only = re.search(r"\by\s*=\s*(\d+(?:\.\d+)?)", prompt, re.IGNORECASE)
    if y_only:
        return Position3D(y=float(y_only.group(1)))
    return Position3D()


def _parse_length_to_mm(value: float, unit: str) -> float:
    u = unit.casefold().replace("'", "").replace('"', "")
    if u in ("m", "meter", "meters", "metre", "metres", "מטר", "מ"):
        return value * 1000.0
    return value


def parse_column_height_mm(prompt: str, default: float = 3500.0) -> float:
    patterns = (
        r"(?:height|high|גובה)\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*(m|meters?|metres?|מטר|מ)(?:\s|$)",
        r"(?:height|high|גובה)\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*mm(?:\s|$)",
        r"(\d+(?:\.\d+)?)\s*(m|meters?|metres?|מטר)\s*(?:high|height|גובה)",
        r"(?:HEB|HEA|IPE|RHS)[\w\d\s]*(?:height|גובה)\s*(\d+(?:\.\d+)?)\s*(?:mm|מ[\"']?מ)?",
        r"(?:height|גובה)\s*(\d+(?:\.\d+)?)\s*(?:mm|מ[\"']?מ)",
    )
    for pattern in patterns:
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if len(m.groups()) >= 2 and m.group(2):
                return _parse_length_to_mm(val, m.group(2))
            return val

    return default


def parse_beam_span_mm(prompt: str, default: float = 6000.0) -> float:
    patterns = (
        r"(?:span|spanning|length|אורך)\s*(?:of\s+)?[:=]?\s*(\d+(?:\.\d+)?)\s*(mm|מ[\"']?מ|m|meters?|metres?|מטר)?",
        r"(?:beam|קורה)[\w\s]*(?:length|span|אורך)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(mm|מ[\"']?מ|m|מטר)?",
        r"spanning\s+(\d+(?:\.\d+)?)\s*(?:mm|m|meters?)?",
        r"(\d+(?:\.\d+)?)\s*mm\s*(?:span|long)",
        r"(?:IPE|HEB|HEA)\s*\d+\s+spanning\s+(\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2) if len(m.groups()) >= 2 else "mm"
            if unit:
                return _parse_length_to_mm(val, unit)
            return val
    return default


def parse_shed_width_mm(prompt: str, default: float = 4000.0) -> float:
    patterns = (
        r"(?:width|wide|רוחב)\s*(?:of\s+)?[:=]?\s*(\d+(?:\.\d+)?)\s*(mm|מ[\"']?מ|m|meters?|metres?|מטר)?",
        r"(\d+(?:\.\d+)?)\s*mm\s*(?:wide|width)",
    )
    for pattern in patterns:
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2) if len(m.groups()) >= 2 else "mm"
            if unit:
                return _parse_length_to_mm(val, unit)
            return val
    return default


def detect_portal_frame_request(prompt: str) -> bool:
    lowered = prompt.casefold()
    has_beam = "beam" in lowered or "קורה" in prompt
    has_column = "column" in lowered or "עמוד" in prompt
    on_top = bool(
        re.search(r"on\s+top|resting\s+on|supported\s+by|על\s+גבי|מעל", prompt, re.IGNORECASE)
    )
    n_columns = re.search(r"(\d+)\s*(?:columns?|עמודים)", prompt, re.IGNORECASE)
    return has_beam and has_column and (on_top or n_columns is not None)


def detect_steel_shed_request(prompt: str) -> bool:
    lowered = prompt.casefold()
    shed_words = ("shed", "warehouse", "hangar", "מבנה", "סככה")
    has_shed_word = any(w in lowered for w in shed_words)
    has_length = any(w in lowered for w in ("length", "span", "spanning", "אורך"))
    has_width = any(w in lowered for w in ("width", "wide", "רוחב"))
    has_columns = "column" in lowered or "עמוד" in prompt
    has_purlins = "purlin" in lowered or "פורלין" in prompt
    return (has_shed_word and has_length and has_width and has_columns) or (has_columns and has_purlins and has_width)


def parse_column_count(prompt: str, default: int = 3) -> int:
    # Avoid matching section sizes like HEB240 column -> 240 columns.
    # Also avoid matching inside numbers (e.g. "240 column" contains "40 column").
    m = re.search(r"(?<![A-Za-z0-9])(\d+)\s*(?:columns?|עמודים)\b", prompt, re.IGNORECASE)
    if m:
        return max(2, int(m.group(1)))
    return default


def build_portal_frame_spec(prompt: str) -> StructuralModelSpec | None:
    """Deterministic portal: N columns on a line + one beam on top."""
    if not detect_portal_frame_request(prompt):
        return None

    n_cols = parse_column_count(prompt, default=3)
    span_mm = parse_beam_span_mm(prompt, default=6000.0)
    col_height_mm = parse_column_height_mm(prompt, default=3500.0)
    base = parse_position(prompt)

    rhs_dims = parse_rhs_dimensions(prompt)
    col_i = parse_i_profile_for_role(prompt, "column")
    beam_i = parse_i_profile_for_role(prompt, "beam")

    col_fallback = fallback_profile("HEB")
    column_profile: ProfileFamily = col_fallback.profile_type
    column_dims = list(col_fallback.dimensions)
    column_key: str | None = col_fallback.profile_key
    if col_i:
        column_profile, column_dims, column_key = col_i
    elif rhs_dims:
        column_profile = "RHS"
        column_dims = rhs_dims
        column_key = f"{int(rhs_dims[0])}x{int(rhs_dims[1])}x{int(rhs_dims[2])}"

    beam_fallback = fallback_profile("IPE")
    beam_profile: ProfileFamily = beam_fallback.profile_type
    beam_dims = list(beam_fallback.dimensions)
    beam_key: str | None = beam_fallback.profile_key
    if beam_i:
        beam_profile, beam_dims, beam_key = beam_i
    elif rhs_dims:
        beam_profile = "RHS"
        beam_dims = rhs_dims
        beam_key = f"{int(rhs_dims[0])}x{int(rhs_dims[1])}x{int(rhs_dims[2])}"

    elements: list[StructuralElement] = []
    for i in range(n_cols):
        x = span_mm * i / (n_cols - 1) if n_cols > 1 else 0.0
        elements.append(
            StructuralElement(
                type="column",
                profile_type=column_profile,
                profile_key=column_key,
                dimensions=column_dims,
                length_mm=col_height_mm,
                position=Position3D(x=x, y=base.y, z=base.z),
            )
        )

    elements.append(
        StructuralElement(
            type="beam",
            profile_type=beam_profile,
            profile_key=beam_key,
            dimensions=beam_dims,
            length_mm=span_mm,
            position=Position3D(x=0.0, y=base.y, z=base.z + col_height_mm),
        )
    )
    return StructuralModelSpec(elements=elements)


def build_rule_fallback_spec(prompt: str) -> StructuralModelSpec | None:
    """Deterministic parser when OpenAI is unavailable."""
    portal = build_portal_frame_spec(prompt)
    if portal is not None:
        return portal

    lowered = prompt.casefold()
    is_column = "column" in lowered or "עמוד" in prompt
    is_beam = "beam" in lowered or "קורה" in prompt
    position = parse_position(prompt)

    rhs_dims = parse_rhs_dimensions(prompt)
    if rhs_dims:
        length = parse_column_height_mm(prompt) if is_column else parse_beam_span_mm(prompt)
        return StructuralModelSpec(
            elements=[
                StructuralElement(
                    type="column" if is_column or not is_beam else "beam",
                    profile_type="RHS",
                    dimensions=rhs_dims,
                    length_mm=length,
                    position=position,
                )
            ]
        )

    i_prof = parse_i_profile(prompt)
    if i_prof:
        family, dims, prof_key = i_prof
        length = parse_column_height_mm(prompt) if is_column or not is_beam else parse_beam_span_mm(prompt)
        return StructuralModelSpec(
            elements=[
                StructuralElement(
                    type="beam" if is_beam and not is_column else "column",
                    profile_type=family,
                    profile_key=prof_key,
                    dimensions=dims,
                    length_mm=length,
                    position=position,
                )
            ]
        )

    if is_column or "עמוד" in prompt:
        col_i = parse_i_profile_for_role(prompt, "column") or parse_i_profile(prompt)
        if col_i:
            family, dims, prof_key = col_i
            return StructuralModelSpec(
                elements=[
                    StructuralElement(
                        type="column",
                        profile_type=family,
                        profile_key=prof_key,
                        dimensions=dims,
                        length_mm=parse_column_height_mm(prompt),
                        position=position,
                    )
                ]
            )
        fb = fallback_profile("HEB")
        return StructuralModelSpec(
            elements=[
                StructuralElement(
                    type="column",
                    profile_type=fb.profile_type,
                    profile_key=fb.profile_key,
                    dimensions=list(fb.dimensions),
                    length_mm=parse_column_height_mm(prompt),
                    position=position,
                )
            ]
        )

    return None


def build_rule_fallback_spec_from_context(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> StructuralModelSpec | None:
    return build_rule_fallback_spec(combined_prompt_for_parsing(prompt, history))


def _dims_differ(a: list[float], b: list[float], rel_tol: float = DIM_REL_TOLERANCE) -> bool:
    if len(a) != len(b):
        return True
    for x, y in zip(a, b):
        if abs(x - y) > rel_tol * max(abs(x), abs(y), 1.0):
            return True
    return False


def _repair_profiles_from_prompt(text: str, elements: list[StructuralElement]) -> None:
    """Apply profile_type + dimensions from the prompt (per column/beam role)."""
    col_i = parse_i_profile_for_role(text, "column")
    beam_i = parse_i_profile_for_role(text, "beam")
    rhs = parse_rhs_dimensions(text)

    for el in elements:
        locked = _profile_from_prompt_for_element(text, el)
        if locked is not None:
            family, dims, prof_key = locked
            el.profile_type = family
            el.dimensions = list(dims)
            if prof_key:
                el.profile_key = prof_key
            continue

        if el.type == "column" and col_i is not None:
            el.profile_type, el.dimensions = col_i[0], list(col_i[1])
            el.profile_key = col_i[2]
        elif el.type == "beam" and beam_i is not None:
            el.profile_type, el.dimensions = beam_i[0], list(beam_i[1])
            el.profile_key = beam_i[2]
        elif rhs is not None and el.profile_type == "RHS" and _dims_differ(el.dimensions, rhs):
            el.dimensions = list(rhs)


def _pick_portal_column_profile(
    text: str, columns: list[StructuralElement]
) -> tuple[ProfileFamily, list[float], str | None]:
    col_i = parse_i_profile_for_role(text, "column")
    if col_i:
        return col_i
    if columns:
        return columns[0].profile_type, list(columns[0].dimensions), columns[0].profile_key
    rhs = parse_rhs_dimensions(text)
    if rhs:
        return "RHS", rhs, f"{int(rhs[0])}x{int(rhs[1])}x{int(rhs[2])}"
    fb = fallback_profile("HEB")
    return fb.profile_type, list(fb.dimensions), fb.profile_key


def _pick_portal_beam_profile(
    text: str, beams: list[StructuralElement]
) -> tuple[ProfileFamily, list[float], str | None]:
    beam_i = parse_i_profile_for_role(text, "beam")
    if beam_i:
        return beam_i
    if beams:
        return beams[0].profile_type, list(beams[0].dimensions), beams[0].profile_key
    rhs = parse_rhs_dimensions(text)
    if rhs:
        return "RHS", rhs, f"{int(rhs[0])}x{int(rhs[1])}x{int(rhs[2])}"
    fb = fallback_profile("IPE")
    return fb.profile_type, list(fb.dimensions), fb.profile_key


def _rebuild_portal_layout(text: str, elements: list[StructuralElement]) -> list[StructuralElement]:
    """Fix column count / beam placement without discarding user-chosen profiles."""
    n_cols = parse_column_count(text)
    span_mm = parse_beam_span_mm(text)
    col_height_mm = parse_column_height_mm(text)
    base = parse_position(text)

    columns = [e for e in elements if e.type == "column"]
    beams = [e for e in elements if e.type == "beam"]

    col_profile, col_dims, col_key = _pick_portal_column_profile(text, columns)
    beam_profile, beam_dims, beam_key = _pick_portal_beam_profile(text, beams)

    if beams and parse_beam_span_mm(text, default=-1.0) <= 0:
        span_mm = beams[0].length_mm
    if columns and parse_column_height_mm(text, default=-1.0) <= 0:
        col_height_mm = columns[0].length_mm

    new_columns: list[StructuralElement] = []
    for i in range(n_cols):
        x = span_mm * i / (n_cols - 1) if n_cols > 1 else 0.0
        new_columns.append(
            StructuralElement(
                type="column",
                profile_type=col_profile,
                profile_key=col_key,
                dimensions=list(col_dims),
                length_mm=col_height_mm,
                position=Position3D(x=x, y=base.y, z=base.z),
            )
        )

    new_beams: list[StructuralElement] = []
    if beams or detect_portal_frame_request(text):
        new_beams.append(
            StructuralElement(
                type="beam",
                profile_type=beam_profile,
                profile_key=beam_key,
                dimensions=list(beam_dims),
                length_mm=span_mm,
                position=Position3D(x=0.0, y=base.y, z=base.z + col_height_mm),
            )
        )

    return new_columns + new_beams


def _repair_lengths_from_prompt(prompt: str, elements: list[StructuralElement]) -> None:
    col_h = parse_column_height_mm(prompt, default=-1.0)
    beam_span = parse_beam_span_mm(prompt, default=-1.0)
    for el in elements:
        if el.type == "column" and col_h > 0:
            if abs(el.length_mm - col_h) > Z_EPS_MM:
                el.length_mm = col_h
        if el.type == "beam" and beam_span > 0:
            if abs(el.length_mm - beam_span) > Z_EPS_MM:
                el.length_mm = beam_span


def _column_top_z(columns: list[StructuralElement]) -> float:
    if not columns:
        return 0.0
    return max(c.position.z + c.length_mm for c in columns)


def _repair_spatial_assembly(text: str, elements: list[StructuralElement]) -> list[StructuralElement]:
    columns = [e for e in elements if e.type == "column"]
    beams = [e for e in elements if e.type == "beam"]

    if detect_portal_frame_request(text):
        expected_n = parse_column_count(text)
        if len(columns) != expected_n or not beams:
            return _rebuild_portal_layout(text, elements)

        span_mm = parse_beam_span_mm(text, default=-1.0)
        if span_mm > 0 and expected_n > 1:
            for i, col in enumerate(sorted(columns, key=lambda c: c.position.x)):
                col.position.x = span_mm * i / (expected_n - 1)

    columns = [e for e in elements if e.type == "column"]
    beams = [e for e in elements if e.type == "beam"]
    top_z = _column_top_z(columns)
    for beam in beams:
        if beam.position.z < top_z - Z_EPS_MM:
            beam.position.z = top_z

    return elements


def _lock_profile_keys_from_prompt(text: str, elements: list[StructuralElement]) -> None:
    """Force catalog keys from prompt per role (overrides wrong LLM keys)."""
    col_key = resolve_from_text_for_role(text, "column")
    beam_key = resolve_from_text_for_role(text, "beam")
    for el in elements:
        if el.type == "column" and col_key:
            el.profile_key = col_key
        elif el.type == "beam" and beam_key:
            el.profile_key = beam_key


def normalize_structural_spec(
    prompt: str,
    spec: StructuralModelSpec,
    history: list[HistoryMessage] | None = None,
) -> StructuralModelSpec:
    """
    Repair LLM output using prompt-locked profiles, lengths, and spatial assembly rules.
    """
    text = combined_prompt_for_parsing(prompt, history)
    elements = [e.model_copy(deep=True) for e in spec.elements]
    _repair_profiles_from_prompt(text, elements)
    _repair_lengths_from_prompt(text, elements)
    elements = _repair_spatial_assembly(text, elements)
    _lock_profile_keys_from_prompt(text, elements)
    spec = StructuralModelSpec(elements=elements)
    return apply_catalog_to_spec(spec, text=text)

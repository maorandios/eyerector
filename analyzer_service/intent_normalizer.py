"""Post-LLM repair of ParametricLayoutRequest (profiles, layout type, dimensions)."""

from __future__ import annotations

import re

from analyzer_service.schemas import HistoryMessage, ParametricLayoutRequest
from analyzer_service.spec_normalizer import (
    combined_prompt_for_parsing,
    detect_portal_frame_request,
    detect_steel_shed_request,
    parse_beam_span_mm,
    parse_column_count,
    parse_column_height_mm,
    parse_shed_width_mm,
)
from analyzer_service.steel_catalog import normalize_profile_name, resolve_from_text, resolve_from_text_for_role


def _profile_after_keyword(prompt: str, keywords: tuple[str, ...]) -> str | None:
    key_pattern = (
        r"(?:IPE|HEA|HEB|HEM|UPN|UPE)\s*\d{2,4}"
        r"|L\s*\d+\s*[xX×/]\s*\d+\s*[xX×/]\s*\d+(?:\.\d+)?"
        r"|CHS\s*\d+(?:\.\d+)?\s*[xX×/]\s*\d+(?:\.\d+)?"
        r"|(?:RHS|SHS)?\s*\d+\s*[xX×/]\s*\d+\s*[xX×/]\s*\d+(?:\.\d+)?"
    )
    for kw in keywords:
        m = re.search(rf"{kw}[^\n\r]{{0,60}}?({key_pattern})", prompt, re.IGNORECASE)
        if m:
            return normalize_profile_name(m.group(1)) or m.group(1)
    return None


def normalize_layout_intent(
    prompt: str,
    intent: ParametricLayoutRequest,
    history: list[HistoryMessage] | None = None,
) -> ParametricLayoutRequest:
    text = combined_prompt_for_parsing(prompt, history)
    data = intent.model_dump()

    if detect_steel_shed_request(text):
        data["layout_type"] = "steel_shed"

    if data.get("layout_type") != "steel_shed" and detect_portal_frame_request(text):
        data["layout_type"] = "portal_frame"

    # Column row: multiple columns + explicit span/length
    lowered = text.casefold()
    mentions_span = any(tok in lowered for tok in ("span", "spanning", "length")) or ("אורך" in text)
    n_cols = parse_column_count(text, default=int(data.get("column_count") or 2))
    if (
        data.get("layout_type") not in ("portal_frame", "steel_shed")
        and n_cols >= 2
        and mentions_span
        and ("column" in lowered or "עמוד" in text)
    ):
        data["layout_type"] = "column_row"

    # Prefer explicit profiles from the *current prompt* over earlier history.
    key = resolve_from_text(prompt) or resolve_from_text_for_role(prompt, "column") or resolve_from_text_for_role(prompt, "beam")
    if key:
        data["profile_name"] = normalize_profile_name(key) or key

    # Per-role sections (e.g. "beam IPE400 on columns HEB300").
    col_key = resolve_from_text_for_role(prompt, "column")
    beam_key = resolve_from_text_for_role(prompt, "beam")
    if col_key:
        data["column_profile_name"] = normalize_profile_name(col_key) or col_key
    if beam_key:
        data["beam_profile_name"] = normalize_profile_name(beam_key) or beam_key
    rafter_key = _profile_after_keyword(prompt, ("rafter", "rafters", "קורה ראשית", "main roof"))
    purlin_key = _profile_after_keyword(prompt, ("purlin", "purlins", "פורלין", "secondary"))
    base_key = _profile_after_keyword(prompt, ("base", "perimeter", "יסוד", "bottom"))
    if rafter_key:
        data["rafter_profile_name"] = rafter_key
    if purlin_key:
        data["purlin_profile_name"] = purlin_key
    if base_key:
        data["base_beam_profile_name"] = base_key

    span = parse_beam_span_mm(text, default=-1.0)
    if span > 0:
        data["total_length_mm"] = span
    width = parse_shed_width_mm(text, default=-1.0)
    if width > 0:
        data["width_mm"] = width
    height = parse_column_height_mm(text, default=-1.0)
    if height > 0:
        data["height_mm"] = height
    if n_cols >= 2:
        data["column_count"] = n_cols
    if data.get("layout_type") == "steel_shed" and int(data.get("column_count") or 0) < 6:
        data["column_count"] = 6

    return ParametricLayoutRequest.model_validate(data)

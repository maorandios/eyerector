"""Rule-based ParametricLayoutRequest when OpenAI is unavailable."""

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
from analyzer_service.steel_catalog import (
    normalize_profile_name,
    fallback_profile,
    resolve_from_text,
    resolve_from_text_for_role,
)


def _profile_after_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    # Match keywords like "purlins using RHS100x100x6".
    key_pattern = (
        r"(?:IPE|HEA|HEB|HEM|UPN|UPE)\s*\d{2,4}"
        r"|L\s*\d+\s*[xX×/]\s*\d+\s*[xX×/]\s*\d+(?:\.\d+)?"
        r"|CHS\s*\d+(?:\.\d+)?\s*[xX×/]\s*\d+(?:\.\d+)?"
        r"|(?:RHS|SHS)?\s*\d+\s*[xX×/]\s*\d+\s*[xX×/]\s*\d+(?:\.\d+)?"
    )
    for kw in keywords:
        m = re.search(rf"{kw}[^\\n\\r]{{0,60}}?({key_pattern})", text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            normalized = normalize_profile_name(raw)
            if normalized:
                return normalized
    return None


def build_layout_intent_from_context(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> ParametricLayoutRequest | None:
    text = combined_prompt_for_parsing(prompt, history or [])

    if detect_steel_shed_request(text):
        col_key = resolve_from_text_for_role(text, "column") or fallback_profile("HEB").profile_key
        beam_key = resolve_from_text_for_role(text, "beam") or fallback_profile("IPE").profile_key
        rafter_key = _profile_after_keyword(text, ("rafter", "rafters", "קורה ראשית", "main roof"))
        purlin_key = _profile_after_keyword(text, ("purlin", "purlins", "פורלין", "secondary"))
        base_key = _profile_after_keyword(text, ("base", "perimeter", "יסוד", "bottom"))
        return ParametricLayoutRequest(
            layout_type="steel_shed",
            profile_name=beam_key,
            column_profile_name=col_key,
            beam_profile_name=beam_key,
            rafter_profile_name=rafter_key,
            purlin_profile_name=purlin_key,
            base_beam_profile_name=base_key,
            column_count=max(6, parse_column_count(text, default=6)),
            height_mm=parse_column_height_mm(text, default=4000.0),
            total_length_mm=parse_beam_span_mm(text, default=12000.0),
            width_mm=parse_shed_width_mm(text, default=6000.0),
            purlin_count=4,
        )

    if detect_portal_frame_request(text):
        # Resolve per-role sections so a beam and its columns can differ
        # (e.g. "beam IPE400 on columns HEB300").
        col_key = resolve_from_text_for_role(text, "column")
        beam_key = resolve_from_text_for_role(text, "beam")
        key = (
            resolve_from_text(prompt)
            or col_key
            or beam_key
            or fallback_profile("HEB").profile_key
        )
        return ParametricLayoutRequest(
            layout_type="portal_frame",
            profile_name=key,
            column_profile_name=col_key,
            beam_profile_name=beam_key,
            column_count=parse_column_count(text),
            height_mm=parse_column_height_mm(text),
            total_length_mm=parse_beam_span_mm(text, default=5000.0),
        )

    lowered = text.casefold()
    is_column = "column" in lowered or "עמוד" in text
    is_beam = "beam" in lowered or "קורה" in text

    # Column row intent: multiple columns + span/length
    if (is_column or is_beam) and (parse_column_count(text) >= 2) and ("span" in lowered or "spanning" in lowered or "length" in lowered or "אורך" in text):
        key = resolve_from_text(prompt) or resolve_from_text_for_role(prompt, "column") or resolve_from_text_for_role(prompt, "beam")
        if not key:
            key = fallback_profile("HEB").profile_key
        return ParametricLayoutRequest(
            layout_type="column_row",
            profile_name=key,
            column_count=parse_column_count(text),
            height_mm=parse_column_height_mm(text, default=3000.0),
            total_length_mm=parse_beam_span_mm(text, default=5000.0),
        )

    if is_column and not is_beam:
        key = resolve_from_text_for_role(prompt, "column") or resolve_from_text(prompt) or fallback_profile("HEB").profile_key
        return ParametricLayoutRequest(
            layout_type="single_element",
            profile_name=key,
            height_mm=parse_column_height_mm(text, default=3000.0),
            total_length_mm=parse_beam_span_mm(text, default=5000.0),
            column_count=parse_column_count(text, default=2),
        )

    key = resolve_from_text(prompt)
    if key:
        return ParametricLayoutRequest(
            layout_type="single_element",
            profile_name=key,
            height_mm=parse_column_height_mm(text, default=3000.0),
            total_length_mm=parse_beam_span_mm(text, default=5000.0),
            column_count=parse_column_count(text, default=2),
        )

    return None

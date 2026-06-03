"""Clean AI PDF extraction payloads before Pydantic validation."""

from __future__ import annotations

import json
import math
from typing import Any

from analyzer_service.schemas import PureStructuralModelSpec

MIN_SEGMENT_LENGTH_MM = 1.0


def _segment_length_mm(element: dict[str, Any]) -> float:
    dx = float(element["end_x"]) - float(element["start_x"])
    dy = float(element["end_y"]) - float(element["start_y"])
    dz = float(element["end_z"]) - float(element["start_z"])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def sanitize_pure_model_payload(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Remove zero-length steel segments and invalid slabs from raw LLM JSON.
    """
    warnings: list[str] = []
    elements_in = data.get("elements") or []
    if not isinstance(elements_in, list):
        raise ValueError("elements must be a list")

    kept_elements: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_el in enumerate(elements_in):
        if not isinstance(raw_el, dict):
            warnings.append(f"Skipped non-object element at index {index}")
            continue
        length = _segment_length_mm(raw_el)
        if length < MIN_SEGMENT_LENGTH_MM:
            warnings.append(
                f"Dropped zero-length member '{raw_el.get('id', f'element_{index}')}' "
                f"(length {length:.4f} mm)"
            )
            continue
        el_id = str(raw_el.get("id") or f"element_{index + 1}")
        if el_id in seen_ids:
            suffix = 2
            while f"{el_id}_{suffix}" in seen_ids:
                suffix += 1
            el_id = f"{el_id}_{suffix}"
            raw_el = {**raw_el, "id": el_id}
            warnings.append(f"Renamed duplicate element id to '{el_id}'")
        seen_ids.add(el_id)
        kept_elements.append(raw_el)

    if not kept_elements:
        raise ValueError(
            "No valid steel segments after removing zero-length members from AI output"
        )

    slabs_in = data.get("slabs")
    kept_slabs: list[dict[str, Any]] | None = None
    if slabs_in:
        kept_slabs = []
        for index, raw_slab in enumerate(slabs_in):
            if not isinstance(raw_slab, dict):
                continue
            try:
                min_x, max_x = float(raw_slab["min_x"]), float(raw_slab["max_x"])
                min_y, max_y = float(raw_slab["min_y"]), float(raw_slab["max_y"])
                min_z, max_z = float(raw_slab["min_z"]), float(raw_slab["max_z"])
            except (KeyError, TypeError, ValueError):
                warnings.append(f"Dropped invalid slab at index {index}")
                continue
            if max_x <= min_x or max_y <= min_y or max_z <= min_z:
                warnings.append(f"Dropped degenerate slab '{raw_slab.get('id', index)}'")
                continue
            kept_slabs.append(raw_slab)

    out = {**data, "elements": kept_elements}
    if kept_slabs is not None:
        out["slabs"] = kept_slabs if kept_slabs else None
    return out, warnings


def parse_pure_model_from_llm_json(raw: str) -> tuple[PureStructuralModelSpec, list[str]]:
    """Parse OpenAI JSON, drop bad segments, then validate."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object")
    cleaned, warnings = sanitize_pure_model_payload(data)
    return PureStructuralModelSpec.model_validate(cleaned), warnings

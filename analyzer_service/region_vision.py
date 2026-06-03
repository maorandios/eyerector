"""Vision analysis of a cropped plan region (Anthropic Claude primary, OpenAI fallback)."""

from __future__ import annotations

import base64
import copy
import json
import os
import re
from pathlib import Path
from typing import Any

from analyzer_service.llm_extractor import LlmExtractionError, _openai_client
from analyzer_service.pdf_extract.vision import _vision_model_candidates
from analyzer_service.region_analysis_schemas import RegionStructuralAnalysis
from analyzer_service.region_layout_compiler import enrich_region_grid_analysis

_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "region_structural_analysis_prompt.txt"
)

_TOOL_NAME = "region_structural_analysis"
# Anthropic retired Claude 3.5 Sonnet API IDs (404). Sonnet 4.6 supports vision + tools.
_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"


def _load_system_prompt() -> str:
    if _PROMPT_PATH.is_file():
        return _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return "Classify the structural region in the crop. Output RegionStructuralAnalysis JSON only."


def _min_confidence() -> float:
    try:
        return float(os.getenv("REGION_MIN_CONFIDENCE", "0.45"))
    except ValueError:
        return 0.45


def _region_vision_provider() -> str:
    return os.getenv("REGION_VISION_PROVIDER", "anthropic").strip().lower() or "anthropic"


def _anthropic_model_candidates() -> list[str]:
    explicit = os.getenv("REGION_VISION_MODEL", "").strip()
    ordered = [
        explicit,
        _DEFAULT_ANTHROPIC_MODEL,
        "claude-sonnet-4-5",
        "claude-3-7-sonnet-20250219",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for name in ordered:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _anthropic_model_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return "not_found" in text or "404" in text


def _inline_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Anthropic tools do not accept $ref; inline $defs from Pydantic JSON schema."""
    root = copy.deepcopy(schema)
    defs = root.pop("$defs", {}) or {}

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                return resolve(defs.get(ref_key, {}))
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(root)


def _anthropic_tool_schema() -> dict[str, Any]:
    schema = RegionStructuralAnalysis.model_json_schema()
    schema = _inline_json_schema(schema)
    schema.pop("title", None)
    schema.pop("description", None)
    return schema


def _anthropic_client():
    try:
        import anthropic
    except ImportError as exc:
        raise LlmExtractionError(
            "anthropic package is not installed. Run: pip install anthropic"
        ) from exc
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise LlmExtractionError(
            "ANTHROPIC_API_KEY is not set. Add it to eyesteel/.env.local for region crop vision."
        )
    return anthropic.Anthropic(api_key=api_key)


def _extract_json_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])
    raise ValueError("no JSON object in model text")


def _finalize_analysis(
    analysis: RegionStructuralAnalysis,
    vision_raw: dict[str, Any],
) -> RegionStructuralAnalysis:
    if analysis.element_type == "grid":
        analysis = enrich_region_grid_analysis(analysis)
    if analysis.confidence < _min_confidence() and not analysis.notes:
        analysis = analysis.model_copy(
            update={
                "notes": (
                    f"Low confidence ({analysis.confidence:.2f}); "
                    "verify parameters or enlarge the crop."
                )
            }
        )
    return analysis


def _parse_region_payload(payload: dict[str, Any]) -> tuple[RegionStructuralAnalysis, dict[str, Any]]:
    vision_raw = RegionStructuralAnalysis.model_validate(payload).model_dump()
    analysis = RegionStructuralAnalysis.model_validate(vision_raw)
    return analysis, vision_raw


def _analyze_with_anthropic(
    png_bytes: bytes,
    *,
    scale_note: str | None,
) -> tuple[RegionStructuralAnalysis, str, dict]:
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    scale = (scale_note or "units mm").strip()
    user_text = (
        f"Scale context: {scale}\n"
        "Analyze this cropped structural plan fragment. "
        "Coordinates are crop-local mm: origin (0,0) at bottom-left of this image, +X right, +Y up.\n"
        "GRID RULES: Read EVERY dimension value along each axis chain (all bay widths between grid lines). "
        "Build x_grid_positions_mm / y_grid_positions_mm as strict cumulative stations from 0 "
        "(e.g. [0, 150, 810, 1460, ...] — never only [0, total_length]). "
        "Also fill x_bay_spacings_mm / y_bay_spacings_mm with ordered bay widths when visible. "
        "Mirror the full station lists in detected_parameters as grid_lines_x_mm and grid_lines_y_mm "
        "comma-separated strings. Count grid lines on the drawing and match array length.\n"
        f"Return structured data using the {_TOOL_NAME} tool only."
    )
    system = _load_system_prompt()
    tool_schema = _anthropic_tool_schema()
    client = _anthropic_client()
    last_error: Exception | None = None
    tried: list[str] = []

    for model_name in _anthropic_model_candidates():
        tried.append(model_name)
        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=8192,
                system=system,
                tools=[
                    {
                        "name": _TOOL_NAME,
                        "description": (
                            "Structural analysis of the cropped plan: grids, sparse column "
                            "indices, and per-mark profiles."
                        ),
                        "input_schema": tool_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": user_text},
                        ],
                    }
                ],
            )
            payload: dict[str, Any] | None = None
            for block in response.content:
                block_type = getattr(block, "type", None)
                if block_type == "tool_use" and getattr(block, "name", None) == _TOOL_NAME:
                    payload = dict(block.input)
                    break
            if payload is None:
                text_parts = [
                    getattr(b, "text", "")
                    for b in response.content
                    if getattr(b, "type", None) == "text"
                ]
                if text_parts:
                    payload = _extract_json_from_text("\n".join(text_parts))
            if payload is None:
                raise LlmExtractionError("Claude returned no region_structural_analysis tool output")

            analysis, vision_raw = _parse_region_payload(payload)
            analysis = _finalize_analysis(analysis, vision_raw)
            return analysis, model_name, vision_raw
        except Exception as exc:
            last_error = exc
            if _anthropic_model_not_found(exc):
                continue
            raise LlmExtractionError(f"Region vision (Claude) failed: {exc}") from exc
    raise LlmExtractionError(
        f"Region vision (Claude) failed after trying {', '.join(tried)}: {last_error}"
    )


def _analyze_with_openai(
    png_bytes: bytes,
    *,
    scale_note: str | None,
) -> tuple[RegionStructuralAnalysis, str, dict]:
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    scale = (scale_note or "units mm").strip()
    user_text = (
        f"Scale context: {scale}\n"
        "Analyze this cropped structural plan fragment and return RegionStructuralAnalysis JSON."
    )
    client = _openai_client()
    last_error: Exception | None = None
    for model_name in _vision_model_candidates():
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _load_system_prompt()},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": _TOOL_NAME,
                        "strict": True,
                        "schema": RegionStructuralAnalysis.openai_strict_json_schema(),
                    },
                },
            )
            raw = completion.choices[0].message.content
            if not raw:
                raise LlmExtractionError("OpenAI returned empty region analysis")
            analysis, vision_raw = _parse_region_payload(
                RegionStructuralAnalysis.model_validate_json(raw).model_dump()
            )
            analysis = _finalize_analysis(analysis, vision_raw)
            return analysis, model_name, vision_raw
        except Exception as exc:
            last_error = exc
            text = str(exc).lower()
            if "model_not_found" in text or "does not have access to model" in text:
                continue
            raise LlmExtractionError(f"Region vision (OpenAI) failed: {exc}") from exc
    raise LlmExtractionError(f"Region vision (OpenAI) failed: {last_error}")


def region_vision_model_label() -> str:
    """Active model id for /health (first configured candidate)."""
    if _region_vision_provider() == "openai":
        candidates = _vision_model_candidates()
        return candidates[0] if candidates else "gpt-4o"
    candidates = _anthropic_model_candidates()
    return candidates[0] if candidates else _DEFAULT_ANTHROPIC_MODEL


def analyze_region_image(
    png_bytes: bytes,
    *,
    scale_note: str | None = None,
) -> tuple[RegionStructuralAnalysis, str, dict]:
    if not png_bytes:
        raise LlmExtractionError("empty crop image")

    provider = _region_vision_provider()
    if provider == "openai":
        return _analyze_with_openai(png_bytes, scale_note=scale_note)
    if provider in ("anthropic", "claude"):
        return _analyze_with_anthropic(png_bytes, scale_note=scale_note)
    raise LlmExtractionError(
        f"Unknown REGION_VISION_PROVIDER={provider!r}. Use 'anthropic' or 'openai'."
    )

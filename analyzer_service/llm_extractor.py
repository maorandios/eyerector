from __future__ import annotations

import json
import os
from pathlib import Path

from openai import APIConnectionError, OpenAI, RateLimitError

from analyzer_service.grid_frame_compiler import GridFrameCompileError, compile_universal_intent_to_ir
from analyzer_service.pure_vector_compiler import compile_universal_intent_to_pure_model
from analyzer_service.intent_fallback import build_layout_intent_from_context
from analyzer_service.schemas import (
    DynamicGraphLayoutRequest,
    HistoryMessage,
    ParametricLayoutRequest,
    PureStructuralModelSpec,
    StructuralIntentIR,
    UniversalStructuralIntent,
)
from analyzer_service.geometry_assignments import normalize_universal_intent_payload
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent
from analyzer_service.steel_catalog import catalog_profile_keys


def _load_env_files() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env.local")
        load_dotenv(root / ".env")
    except ImportError:
        pass


_load_env_files()

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
MAX_HISTORY_TURNS = 12

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "parametric_intent_prompt.txt"
_GRAPH_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "graph_intent_prompt.txt"
_IR_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "universal_structural_intent_prompt.txt"
_PURE_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "pure_structural_model_prompt.txt"


def _catalog_index_for_prompt() -> str:
    return ", ".join(catalog_profile_keys())


def _load_system_prompt() -> str:
    base = (
        "You extract structural layout intent as ParametricLayoutRequest JSON. "
        "Never output 3D coordinates."
    )
    if _PROMPT_PATH.is_file():
        base = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return f"{base}\n\nALLOWED catalog profile examples:\n{_catalog_index_for_prompt()}"


SYSTEM_PROMPT = _load_system_prompt()


def _load_graph_system_prompt() -> str:
    base = (
        "You are a structural graph compiler. "
        "Break the user request into columns as nodes and beams as relationships."
    )
    if _GRAPH_PROMPT_PATH.is_file():
        base = _GRAPH_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return f"{base}\n\nALLOWED catalog profile examples:\n{_catalog_index_for_prompt()}"


GRAPH_SYSTEM_PROMPT = _load_graph_system_prompt()


def _load_universal_intent_prompt() -> str:
    base = (
        "You are a structural intent extractor. "
        "Output only UniversalStructuralIntent JSON with levels, grid, and structural groups. "
        "Never output absolute coordinates."
    )
    if _IR_PROMPT_PATH.is_file():
        base = _IR_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return f"{base}\n\nALLOWED catalog profile examples:\n{_catalog_index_for_prompt()}"


UNIVERSAL_INTENT_PROMPT = _load_universal_intent_prompt()


def _load_pure_vector_prompt() -> str:
    base = (
        "You extract structural geometry as PureStructuralModelSpec JSON: "
        "line segments with profile_name and absolute coordinates only."
    )
    if _PURE_PROMPT_PATH.is_file():
        base = _PURE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return f"{base}\n\nALLOWED catalog profile examples:\n{_catalog_index_for_prompt()}"


PURE_VECTOR_PROMPT = _load_pure_vector_prompt()


class LlmExtractionError(Exception):
    """Raised when structured extraction from the LLM fails."""


def _openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LlmExtractionError(
            "OPENAI_API_KEY is not set. Add it to your environment to enable chat-to-IFC generation."
        )
    return OpenAI(api_key=api_key)


def _format_history(history: list[HistoryMessage]) -> str:
    if not history:
        return "(no prior messages)"
    lines: list[str] = []
    for msg in history[-MAX_HISTORY_TURNS:]:
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.text}")
    return "\n".join(lines)


def _rule_fallback_allowed() -> bool:
    return os.getenv("CHAT_TO_IFC_RULE_FALLBACK", "").strip().lower() in ("1", "true", "yes")


def _try_rule_fallback(
    prompt: str,
    history: list[HistoryMessage] | None = None,
    *,
    force: bool = False,
) -> ParametricLayoutRequest | None:
    if not force and not _rule_fallback_allowed():
        return None
    return build_layout_intent_from_context(prompt, history)


def _llm_error_allows_auto_fallback(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError)):
        return True
    text = str(exc).lower()
    return "insufficient_quota" in text or "rate_limit" in text or "quota" in text


def extract_layout_intent(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> ParametricLayoutRequest:
    """
    Extract parametric layout intent (no coordinates) using OpenAI strict JSON schema.
    Falls back to rule-based parsing on quota/connection errors or CHAT_TO_IFC_RULE_FALLBACK=1.
    """
    history = history or []
    user_content = f"Current request:\n{prompt.strip()}\n\nConversation history:\n{_format_history(history)}"

    # Deterministic pre-pass: if rules can classify a template (column_row/portal_frame),
    # prefer it over the LLM to avoid misclassification.
    rule_intent = build_layout_intent_from_context(prompt, history)
    if rule_intent is not None and rule_intent.layout_type in ("portal_frame", "column_row"):
        return rule_intent

    try:
        client = _openai_client()
        model_name = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL

        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "parametric_layout_request",
                    "strict": True,
                    "schema": ParametricLayoutRequest.openai_strict_json_schema(),
                },
            },
        )
        raw = completion.choices[0].message.content
        if not raw:
            raise LlmExtractionError("OpenAI returned empty content")
        return ParametricLayoutRequest.model_validate_json(raw)
    except LlmExtractionError:
        raise
    except Exception as exc:
        force_fallback = _llm_error_allows_auto_fallback(exc)
        fallback = _try_rule_fallback(prompt, history, force=force_fallback)
        if fallback is not None:
            return fallback
        hint = ""
        if force_fallback:
            hint = " OpenAI quota/billing issue detected; rule fallback could not parse this prompt."
        raise LlmExtractionError(f"LLM extraction failed: {exc}.{hint}") from exc


def extract_dynamic_graph_layout(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> DynamicGraphLayoutRequest:
    """
    Extract DynamicGraphLayoutRequest using strict JSON schema.
    """
    history = history or []
    user_content = f"Current request:\n{prompt.strip()}\n\nConversation history:\n{_format_history(history)}"
    try:
        client = _openai_client()
        model_name = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": GRAPH_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "dynamic_graph_layout_request",
                    "strict": True,
                    "schema": DynamicGraphLayoutRequest.openai_strict_json_schema(),
                },
            },
        )
        raw = completion.choices[0].message.content
        if not raw:
            raise LlmExtractionError("OpenAI returned empty graph content")
        return DynamicGraphLayoutRequest.model_validate_json(raw)
    except Exception as exc:
        raise LlmExtractionError(f"LLM graph extraction failed: {exc}") from exc


def extract_universal_structural_intent(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> UniversalStructuralIntent:
    """
    Extract neutral UniversalStructuralIntent (levels + grid + groups).
    Structured engineering prompts are parsed deterministically; otherwise use LLM.
    """
    structured = parse_structured_prompt_to_universal_intent(prompt)
    if structured is not None:
        return structured

    history = history or []
    user_content = f"Current request:\n{prompt.strip()}\n\nConversation history:\n{_format_history(history)}"
    try:
        client = _openai_client()
        model_name = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": UNIVERSAL_INTENT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "universal_structural_intent",
                    "strict": True,
                    "schema": UniversalStructuralIntent.openai_strict_json_schema(),
                },
            },
        )
        raw = completion.choices[0].message.content
        if not raw:
            raise LlmExtractionError("OpenAI returned empty UniversalStructuralIntent content")
        payload = normalize_universal_intent_payload(json.loads(raw))
        return UniversalStructuralIntent.model_validate(payload)
    except Exception as exc:
        raise LlmExtractionError(f"LLM UniversalStructuralIntent extraction failed: {exc}") from exc


def extract_pure_structural_model(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> PureStructuralModelSpec:
    """
    General pipeline: UniversalStructuralIntent → geometry expansion → pure segments.
    Does not ask the LLM for hundreds of coordinates (incomplete on large models).
    """
    universal = extract_universal_structural_intent(prompt, history)
    try:
        return compile_universal_intent_to_pure_model(universal)
    except GridFrameCompileError as exc:
        raise LlmExtractionError(f"Geometry compilation failed: {exc}") from exc


def extract_structural_intent_ir(
    prompt: str,
    history: list[HistoryMessage] | None = None,
) -> StructuralIntentIR:
    """Legacy: semantic grid-frame compiler IR. Prefer extract_pure_structural_model()."""
    universal = extract_universal_structural_intent(prompt, history)
    try:
        return compile_universal_intent_to_ir(universal)
    except GridFrameCompileError as exc:
        raise LlmExtractionError(f"Grid frame compilation failed: {exc}") from exc


# Backward compatibility for tests/tools that still import the old name.
def extract_structural_spec(
    prompt: str,
    history: list[HistoryMessage] | None = None,
):
    """Deprecated: use extract_layout_intent + normalize_layout_intent + compile_layout_to_spec."""
    from analyzer_service.intent_normalizer import normalize_layout_intent
    from analyzer_service.layout_templates import compile_layout_to_spec

    intent = extract_layout_intent(prompt, history)
    intent = normalize_layout_intent(prompt, intent, history)
    return compile_layout_to_spec(intent)

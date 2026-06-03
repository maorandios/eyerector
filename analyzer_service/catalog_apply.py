"""Apply steel catalog resolution to structural specs."""

from __future__ import annotations

from typing import Literal

from analyzer_service.schemas import StructuralElement, StructuralModelSpec
from analyzer_service.steel_catalog import (
    ResolvedProfile,
    apply_catalog_to_element as resolve_catalog_profile,
    resolve_from_text_for_role,
)


def apply_catalog_to_element(
    element: StructuralElement,
    *,
    text: str | None = None,
) -> StructuralElement:
    role: Literal["column", "beam"] = "column" if element.type == "column" else "beam"
    profile_key = element.profile_key

    # Prompt text wins over LLM profile_key when user named a section explicitly.
    if text:
        from_text = resolve_from_text_for_role(text, role)
        if from_text:
            profile_key = from_text

    resolved: ResolvedProfile = resolve_catalog_profile(
        profile_key=profile_key,
        profile_type=element.profile_type,
        dimensions=list(element.dimensions),
    )

    element.profile_key = resolved.profile_key
    element.profile_type = resolved.profile_type
    element.dimensions = list(resolved.dimensions)
    return element


def apply_catalog_to_spec(
    spec: StructuralModelSpec,
    *,
    text: str | None = None,
) -> StructuralModelSpec:
    elements = [apply_catalog_to_element(e.model_copy(deep=True), text=text) for e in spec.elements]
    return StructuralModelSpec(elements=elements)

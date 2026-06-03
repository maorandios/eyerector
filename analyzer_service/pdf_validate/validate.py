"""Validate PureStructuralModelSpec before IFC export."""

from __future__ import annotations

from dataclasses import dataclass, field

from analyzer_service.schemas import PureStructuralModelSpec
from analyzer_service.steel_catalog import resolve_profile_key


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    element_count: int = 0
    slab_count: int = 0


def validate_pure_model(model: PureStructuralModelSpec) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    if not model.elements:
        errors.append("model.elements must contain at least one steel segment")

    ids: list[str] = []
    for element in model.elements:
        ids.append(element.id)
        length = (
            (element.end_x - element.start_x) ** 2
            + (element.end_y - element.start_y) ** 2
            + (element.end_z - element.start_z) ** 2
        ) ** 0.5
        if length < 1.0:
            errors.append(f"element '{element.id}' has near-zero length ({length:.3f} mm)")
        try:
            resolve_profile_key(element.profile_name)
        except Exception:
            warnings.append(f"profile '{element.profile_name}' on '{element.id}' is not in steel catalog")

    if len(set(ids)) != len(ids):
        errors.append("duplicate element ids")

    slab_count = len(model.slabs or [])
    for slab in model.slabs or []:
        if slab.max_x <= slab.min_x or slab.max_y <= slab.min_y or slab.max_z <= slab.min_z:
            errors.append(f"slab '{slab.id}' has invalid bounding box")

    return ValidationReport(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        element_count=len(model.elements),
        slab_count=slab_count,
    )

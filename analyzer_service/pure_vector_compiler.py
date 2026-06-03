"""
Pure vector compiler: maps line segments + slab boxes to IFC-ready StructuralModelSpec.

No architectural vocabulary (roof, truss, mezzanine, etc.) is interpreted here.
IFC entity kind (column vs beam) is inferred only from segment geometry.
"""

from __future__ import annotations

import math

from analyzer_service.catalog_apply import apply_catalog_to_element
from analyzer_service.grid_frame_compiler import GridFrameCompileError, compile_universal_intent_to_ir
from analyzer_service.schemas import (
    IndependentElementSpec,
    Position3D,
    PureSlabBoxSpec,
    PureSteelElementSpec,
    PureStructuralModelSpec,
    StructuralElement,
    StructuralIntentIR,
    StructuralModelSpec,
    UniversalStructuralIntent,
)
from analyzer_service.steel_catalog import normalize_profile_name, resolve_profile_key

Z_EPS_MM = 0.5
VERTICAL_RATIO = 0.95


class PureVectorCompileError(Exception):
    """Raised when pure vector data cannot be compiled to a structural spec."""


def ir_to_pure_model(ir: StructuralIntentIR) -> PureStructuralModelSpec:
    """Convert legacy categorized IR into pure segments (drops semantic category)."""
    elements = [
        PureSteelElementSpec(
            id=e.id,
            profile_name=e.profile_name,
            start_x=e.start_x,
            start_y=e.start_y,
            start_z=e.start_z,
            end_x=e.end_x,
            end_y=e.end_y,
            end_z=e.end_z,
            up_vector_z=1.0,
        )
        for e in ir.independent_elements
        if e.category != "slab"
    ]
    slabs: list[PureSlabBoxSpec] = []
    for e in ir.independent_elements:
        if e.category != "slab":
            continue
        slabs.append(
            PureSlabBoxSpec(
                id=e.id,
                min_x=min(e.start_x, e.end_x),
                min_y=min(e.start_y, e.end_y),
                min_z=min(e.start_z, e.end_z),
                max_x=max(e.start_x, e.end_x),
                max_y=max(e.start_y, e.end_y),
                max_z=max(e.start_z, e.end_z),
            )
        )
    if not elements:
        raise PureVectorCompileError("No steel segments in legacy IR")
    return PureStructuralModelSpec(elements=elements, slabs=slabs or None)


def _profile_fields(profile_name: str) -> tuple[str, list[float], str]:
    raw = (profile_name or "").strip() or "HEB200"
    for key in dict.fromkeys([raw, normalize_profile_name(raw) or ""]):
        if not key:
            continue
        try:
            resolved = resolve_profile_key(key)
            return resolved.profile_type, list(resolved.dimensions), resolved.profile_key
        except KeyError:
            pass
    fallback = resolve_profile_key("HEB200")
    return fallback.profile_type, list(fallback.dimensions), fallback.profile_key


def _segment_length(el: PureSteelElementSpec) -> float:
    dx = float(el.end_x) - float(el.start_x)
    dy = float(el.end_y) - float(el.start_y)
    dz = float(el.end_z) - float(el.start_z)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _is_vertical_segment(el: PureSteelElementSpec, length: float) -> bool:
    if length <= Z_EPS_MM:
        return False
    dz = abs(float(el.end_z) - float(el.start_z))
    plan = math.hypot(float(el.end_x) - float(el.start_x), float(el.end_y) - float(el.start_y))
    return dz / length >= VERTICAL_RATIO and plan <= Z_EPS_MM


def pure_steel_to_structural_element(el: PureSteelElementSpec) -> StructuralElement:
    """Map one line segment to StructuralElement using geometry only."""
    sx, sy, sz = float(el.start_x), float(el.start_y), float(el.start_z)
    ex, ey, ez = float(el.end_x), float(el.end_y), float(el.end_z)
    length = _segment_length(el)
    if length <= Z_EPS_MM:
        raise PureVectorCompileError(f"Element '{el.id}' has zero length")

    profile_type, dims, profile_key = _profile_fields(el.profile_name)

    if _is_vertical_segment(el, length):
        base_z = min(sz, ez)
        return StructuralElement(
            type="column",
            profile_type=profile_type,  # type: ignore[arg-type]
            profile_key=profile_key,
            dimensions=dims,
            length_mm=length,
            position=Position3D(x=sx, y=sy, z=base_z),
        )

    dx, dy, dz = ex - sx, ey - sy, ez - sz
    direction = [dx / length, dy / length, dz / length]
    beam_axis = "X" if abs(dx) >= abs(dy) else "Y"
    return StructuralElement(
        type="beam",
        profile_type=profile_type,  # type: ignore[arg-type]
        profile_key=profile_key,
        dimensions=dims,
        length_mm=length,
        beam_axis=beam_axis,  # type: ignore[arg-type]
        beam_direction_vector=direction,
        position=Position3D(x=sx, y=sy, z=sz),
    )


def pure_slab_to_structural_element(slab: PureSlabBoxSpec | dict[str, float | str]) -> StructuralElement:
    if isinstance(slab, PureSlabBoxSpec):
        box = slab
    else:
        box = PureSlabBoxSpec(
            id=str(slab["id"]),
            min_x=float(slab["min_x"]),
            min_y=float(slab["min_y"]),
            min_z=float(slab["min_z"]),
            max_x=float(slab["max_x"]),
            max_y=float(slab["max_y"]),
            max_z=float(slab["max_z"]),
        )
    length_x = abs(box.max_x - box.min_x)
    width_y = abs(box.max_y - box.min_y)
    thickness = abs(box.max_z - box.min_z)
    if length_x <= Z_EPS_MM or width_y <= Z_EPS_MM or thickness <= Z_EPS_MM:
        raise PureVectorCompileError(f"Slab '{box.id}' must have positive extent on all axes")
    top_z = max(box.min_z, box.max_z)
    cx = (box.min_x + box.max_x) / 2.0
    cy = (box.min_y + box.max_y) / 2.0
    return StructuralElement(
        type="slab",
        profile_type="RHS",
        profile_key="CONCRETE_SLAB",
        dimensions=[length_x, width_y, thickness],
        length_mm=thickness,
        position=Position3D(x=cx, y=cy, z=top_z),
    )


def compile_pure_to_spec(model: PureStructuralModelSpec) -> StructuralModelSpec:
    """Compile pure vector model to StructuralModelSpec (geometry-only classification)."""
    elements: list[StructuralElement] = []
    for segment in model.elements:
        element = pure_steel_to_structural_element(segment)
        if element.type != "slab":
            element = apply_catalog_to_element(element)
        elements.append(element)
    if model.slabs:
        for slab in model.slabs:
            elements.append(pure_slab_to_structural_element(slab))
    if not elements:
        raise PureVectorCompileError("PureStructuralModelSpec produced no IFC elements")
    return StructuralModelSpec(elements=elements)


def legacy_independent_to_pure(elements: list[IndependentElementSpec]) -> PureStructuralModelSpec:
    ir = StructuralIntentIR(independent_elements=elements)
    return ir_to_pure_model(ir)


def compile_universal_intent_to_pure_model(intent: UniversalStructuralIntent) -> PureStructuralModelSpec:
    """Expand neutral grid intent to absolute segments, then strip semantic categories."""
    ir = compile_universal_intent_to_ir(intent)
    return ir_to_pure_model(ir)

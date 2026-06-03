"""
Build IFC4 steel models from StructuralModelSpec using the official steel catalog.

- Columns: extruded vertically (+Z) from position (x, y, z) for length_mm (height).
- Beams: extruded horizontally (+X or +Y) from position for length_mm (span).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate as aggregate
import ifcopenshell.api.context as context
import ifcopenshell.api.geometry as geometry
import ifcopenshell.api.project as project
import ifcopenshell.api.pset as pset
import ifcopenshell.api.root as root
import ifcopenshell.api.spatial as spatial
import ifcopenshell.api.unit as unit
import numpy as np

from analyzer_service.catalog_apply import apply_catalog_to_element
from analyzer_service.pure_vector_compiler import (
    PureVectorCompileError,
    compile_pure_to_spec,
    ir_to_pure_model,
)
from analyzer_service.schemas import (
    DynamicGraphLayoutRequest,
    Position3D,
    PureStructuralModelSpec,
    StructuralElement,
    StructuralIntentIR,
    StructuralModelSpec,
)
from analyzer_service.steel_catalog import profile_shape, resolve_profile_key

# Beam extrusion along +X: profile Z -> world X, profile X -> world Y
BEAM_AXIS_X: tuple[tuple[float, float, float], tuple[float, float, float]] = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
)
BEAM_AXIS_Y: tuple[tuple[float, float, float], tuple[float, float, float]] = (
    (0.0, 1.0, 0.0),
    (1.0, 0.0, 0.0),
)

Z_EPS_MM = 0.5

# ifcopenshell's geometry API expects extrusion depth in SI metres and converts
# it to the file's length unit (mm) internally. Our model is authored in mm, so
# we must convert mm -> m before calling add_profile_representation.
MM_PER_M = 1000.0


class IfcGenerationError(Exception):
    """Raised when IFC model construction or validation fails."""


def _extract_mm(prompt: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def _extract_count(prompt: str, patterns: list[str]) -> int | None:
    for pattern in patterns:
        m = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
        if m:
            return int(m.group(1))
    return None


def _extract_column_count(prompt: str) -> int | None:
    """
    Column totals from prompt text.

    Warehouse / portal prompts often specify N columns per side wall (front + back).
    A loose ``(\\d+) columns`` match would under-count (17 vs 34).
    """
    front = re.search(
        r"(?:Place\s+)?(\d+)\s+columns?\b[\s\S]{0,80}?\bfront\b",
        prompt,
        re.IGNORECASE,
    )
    back = re.search(
        r"(\d+)\s+(?:matching\s+)?columns?\b[\s\S]{0,80}?\bback\b",
        prompt,
        re.IGNORECASE,
    )
    if front and back:
        return int(front.group(1)) + int(back.group(1))

    per_wall = re.findall(
        r"(\d+)\s+columns?\s+(?:along|on)\s+(?:each\s+)?(?:side|long)\s+wall",
        prompt,
        re.IGNORECASE,
    )
    if len(per_wall) == 1:
        return int(per_wall[0]) * 2

    return _extract_count(
        prompt,
        [
            r"SUPPORT COLUMNS[\s\S]{0,140}?-\s*(\d+)\s*Units",
            r"(\d+)\s*columns?\b",
        ],
    )


def _parse_prompt_constraints(prompt: str) -> dict[str, float | int]:
    constraints: dict[str, float | int] = {}

    span_x = _extract_mm(
        prompt,
        [
            r"Mezzanine Total Length[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
            r"Total Length[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
            r"Length[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
        ],
    )
    if span_x is not None:
        constraints["span_x_mm"] = span_x

    span_y = _extract_mm(
        prompt,
        [
            r"Mezzanine Total Width[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
            r"Total Width[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
            r"Width[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
        ],
    )
    if span_y is not None:
        constraints["span_y_mm"] = span_y

    bay_spacing = _extract_mm(prompt, [r"Bay Spacing[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm"])
    if bay_spacing is not None:
        constraints["bay_spacing_x_mm"] = bay_spacing

    deck_top = _extract_mm(
        prompt,
        [
            r"Finished Deck Elevation[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
            r"top face at Z\s*=\s*(\d+(?:\.\d+)?)",
        ],
    )
    if deck_top is not None:
        constraints["deck_top_elevation_mm"] = deck_top

    col_top = _extract_mm(prompt, [r"from Z=0 to Z=(\d+(?:\.\d+)?)", r"Column tops stop at Z=(\d+(?:\.\d+)?)"])
    if col_top is not None:
        constraints["column_top_mm"] = col_top

    slab_t = _extract_mm(prompt, [r"Thickness\s*=\s*(\d+(?:\.\d+)?)\s*mm"])
    if slab_t is not None:
        constraints["slab_thickness_mm"] = slab_t

    primary_depth = _extract_mm(prompt, [r"HEB200\s*\(\s*(\d+(?:\.\d+)?)\s*mm\s*depth"])
    if primary_depth is not None:
        constraints["primary_beam_depth_mm"] = primary_depth

    column_count = _extract_column_count(prompt)
    if column_count is not None:
        constraints["count_columns"] = column_count

    mappings: dict[str, list[str]] = {
        "primary_beams": [r"MAIN GIRDERS[\s\S]{0,140}?-\s*(\d+)\s*Units"],
        "secondary_beams": [r"FLOOR JOISTS[\s\S]{0,140}?-\s*(\d+)\s*Lines"],
        "bracing": [r"KNEE BRACES[\s\S]{0,140}?Add\s*(\d+)\s*diagonal"],
    }
    for class_name, patterns in mappings.items():
        count = _extract_count(prompt, patterns)
        if count is not None:
            constraints[f"count_{class_name}"] = count

    # Slab is explicitly requested when "IfcSlab" appears.
    if re.search(r"IfcSlab|MEZZANINE FLOOR DECK|משטח הגלריה", prompt, re.IGNORECASE):
        constraints["count_slabs"] = 1

    return constraints


def _write_model_to_bytes(model: ifcopenshell.file) -> bytes:
    fd, path_str = tempfile.mkstemp(suffix=".ifc")
    path = Path(path_str)
    try:
        os.close(fd)
        model.write(str(path))
        data = path.read_bytes()
    finally:
        path.unlink(missing_ok=True)

    if not data:
        raise IfcGenerationError("IFC serialization produced empty output")

    _validate_ifc_bytes(data)
    return data


def _validate_ifc_bytes(data: bytes) -> None:
    fd, path_str = tempfile.mkstemp(suffix=".ifc")
    path = Path(path_str)
    try:
        os.close(fd)
        path.write_bytes(data)
        opened = ifcopenshell.open(str(path))
        if len(opened.by_type("IfcProduct")) < 1:
            raise IfcGenerationError("Generated IFC contains no IfcProduct instances")
    except IfcGenerationError:
        raise
    except Exception as exc:
        raise IfcGenerationError(f"Generated IFC failed validation: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)


def _create_spatial_structure(
    model: ifcopenshell.file,
) -> tuple[ifcopenshell.entity_instance, ifcopenshell.entity_instance]:
    project_entity = root.create_entity(model, ifc_class="IfcProject", name="EyeSteel AI Model")
    unit.assign_unit(model, length={"is_metric": True, "raw": "MILLIMETRES"})

    model_ctx = context.add_context(model, context_type="Model")
    try:
        model_context = context.add_context(
            model,
            context_type="Model",
            context_identifier="Body",
            parent=model_ctx,
        )
    except Exception:
        model_context = model_ctx

    site = root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = root.create_entity(model, ifc_class="IfcBuilding", name="Building")
    storey = root.create_entity(model, ifc_class="IfcBuildingStorey", name="Ground Floor")

    aggregate.assign_object(model, relating_object=project_entity, products=[site])
    aggregate.assign_object(model, relating_object=site, products=[building])
    aggregate.assign_object(model, relating_object=building, products=[storey])

    return model_context, storey


def _resolved_element(element: StructuralElement) -> StructuralElement:
    return apply_catalog_to_element(element.model_copy(deep=True))


def _profile_label(element: StructuralElement) -> str:
    if element.type == "slab":
        return "SLAB"
    if element.profile_key:
        return element.profile_key
    dims = element.dimensions
    shape = profile_shape(element.profile_type)
    if shape == "RHS":
        return f"{int(dims[0])}x{int(dims[1])}x{int(dims[2])}"
    if shape == "CHS":
        return f"CHS{dims[0]}x{dims[1]}"
    if shape == "L":
        return f"L{int(dims[0])}x{int(dims[1])}x{int(dims[2])}"
    return (
        f"{element.profile_type}{int(dims[0])}x{int(dims[1])}"
        f"x{int(dims[2])}x{int(dims[3])}"
    )


def _create_profile(model: ifcopenshell.file, element: StructuralElement) -> ifcopenshell.entity_instance:
    label = _profile_label(element)
    dims = element.dimensions
    shape = profile_shape(element.profile_type)

    if shape == "RHS":
        width, depth, wall = dims[0], dims[1], dims[2]
        return model.create_entity(
            "IfcRectangleHollowProfileDef",
            ProfileName=label,
            ProfileType="AREA",
            XDim=width,
            YDim=depth,
            WallThickness=wall,
        )

    if shape == "CHS":
        outer_diameter, wall = dims[0], dims[1]
        return model.create_entity(
            "IfcCircleHollowProfileDef",
            ProfileName=label,
            ProfileType="AREA",
            Radius=outer_diameter / 2.0,
            WallThickness=wall,
        )

    if shape == "L":
        depth, width, thickness = dims[0], dims[1], dims[2]
        return model.create_entity(
            "IfcLShapeProfileDef",
            ProfileName=label,
            ProfileType="AREA",
            Depth=depth,
            Width=width,
            Thickness=thickness,
        )

    if shape == "U":
        depth, flange_width, web, flange = dims[0], dims[1], dims[2], dims[3]
        return model.create_entity(
            "IfcUShapeProfileDef",
            ProfileName=label,
            ProfileType="AREA",
            Depth=depth,
            FlangeWidth=flange_width,
            WebThickness=web,
            FlangeThickness=flange,
        )

    overall_depth, overall_width, web, flange = dims[0], dims[1], dims[2], dims[3]
    return model.create_entity(
        "IfcIShapeProfileDef",
        ProfileName=label,
        ProfileType="AREA",
        OverallDepth=overall_depth,
        OverallWidth=overall_width,
        WebThickness=web,
        FlangeThickness=flange,
    )


def _placement_matrix(element: StructuralElement) -> np.ndarray:
    """4x4 translation matrix in millimetres (is_si=False in ifcopenshell API)."""
    matrix = np.eye(4, dtype=float)
    matrix[0, 3] = float(element.position.x)
    matrix[1, 3] = float(element.position.y)
    matrix[2, 3] = float(element.position.z)
    return matrix


def _beam_placement_axes(element: StructuralElement) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if element.beam_direction_vector is not None:
        z_axis = np.array(element.beam_direction_vector, dtype=float)
        z_norm = np.linalg.norm(z_axis)
        if z_norm <= 0:
            raise IfcGenerationError("Invalid beam direction vector: zero magnitude")
        z_axis = z_axis / z_norm

        up = np.array([0.0, 0.0, 1.0], dtype=float)
        if abs(float(np.dot(z_axis, up))) >= 0.999:
            up = np.array([1.0, 0.0, 0.0], dtype=float)
        x_axis = np.cross(up, z_axis)
        x_norm = np.linalg.norm(x_axis)
        if x_norm <= 0:
            raise IfcGenerationError("Invalid beam direction vector: cannot derive profile axis")
        x_axis = x_axis / x_norm
        return (
            (float(z_axis[0]), float(z_axis[1]), float(z_axis[2])),
            (float(x_axis[0]), float(x_axis[1]), float(x_axis[2])),
        )
    if element.beam_axis == "Y":
        return BEAM_AXIS_Y
    return BEAM_AXIS_X


def _column_top_z(columns: list[StructuralElement]) -> float:
    if not columns:
        return 0.0
    return max(float(c.position.z) + float(c.length_mm) for c in columns)


def _column_base_z(columns: list[StructuralElement]) -> float:
    if not columns:
        return 0.0
    return min(float(c.position.z) for c in columns)


def _assert_beam_on_column_tops(spec: StructuralModelSpec, beam: StructuralElement) -> None:
    if beam.beam_direction_vector is not None:
        # Graph beams can be inclined and not necessarily at global top Z.
        return
    columns = [e for e in spec.elements if e.type == "column"]
    if not columns:
        return
    base_z = _column_base_z(columns)
    # Allow perimeter/base tie beams at foundation level.
    if abs(float(beam.position.z) - base_z) <= Z_EPS_MM:
        return
    top_z = _column_top_z(columns)
    if beam.position.z + Z_EPS_MM < top_z:
        raise IfcGenerationError(
            f"Beam placement z={beam.position.z} mm must be at column top z={top_z} mm "
            f"(expected beam origin at (0, 0, height_mm))."
        )


def _add_element(
    model: ifcopenshell.file,
    *,
    model_context: ifcopenshell.entity_instance,
    storey: ifcopenshell.entity_instance,
    element: StructuralElement,
    index: int,
    all_elements: list[StructuralElement],
) -> ifcopenshell.entity_instance:
    element = _resolved_element(element)
    profile = _create_profile(model, element)
    label = _profile_label(element)

    extrusion_depth_mm = float(element.length_mm)
    extrusion_depth_m = extrusion_depth_mm / MM_PER_M

    if element.type == "column":
        rep_kwargs: dict = {
            "context": model_context,
            "profile": profile,
            "depth": extrusion_depth_m,
        }
        placement = _placement_matrix(element)
        length_tag = f"H{int(extrusion_depth_mm)}"
    elif element.type == "beam":
        _assert_beam_on_column_tops(
            StructuralModelSpec(elements=all_elements),
            element,
        )
        rep_kwargs = {
            "context": model_context,
            "profile": profile,
            "depth": extrusion_depth_m,
            "placement_zx_axes": _beam_placement_axes(element),
        }
        placement = _placement_matrix(element)
        length_tag = f"L{int(extrusion_depth_mm)}"
    elif element.type == "slab":
        length_mm, width_mm, thickness_mm = float(element.dimensions[0]), float(element.dimensions[1]), float(element.dimensions[2])
        profile = model.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=length_mm,
            YDim=width_mm,
            ProfileName="SLAB",
        )
        rep_kwargs = {
            "context": model_context,
            "profile": profile,
            "depth": thickness_mm / MM_PER_M,
            # Extrude downwards so slab top remains at element.position.z
            "placement_zx_axes": ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)),
        }
        placement = _placement_matrix(element)
        length_tag = f"T{int(thickness_mm)}"
    else:
        raise IfcGenerationError(f"Unsupported element type: {element.type}")

    if element.type == "column":
        class_label = "Column"
        ifc_class = "IfcColumn"
    elif element.type == "beam":
        class_label = "Beam"
        ifc_class = "IfcBeam"
    else:
        class_label = "Slab"
        ifc_class = "IfcSlab"
    name = f"{class_label} {index} {length_tag} ({label})"
    product = root.create_entity(model, ifc_class=ifc_class, name=name)

    representation = geometry.add_profile_representation(model, **rep_kwargs)
    geometry.assign_representation(model, product=product, representation=representation)
    spatial.assign_container(model, relating_structure=storey, products=[product])
    geometry.edit_object_placement(
        model,
        product=product,
        matrix=placement,
        is_si=False,
    )
    _attach_steel_pset(model, product, element, label)
    return product


def _attach_steel_pset(
    model: ifcopenshell.file,
    product: ifcopenshell.entity_instance,
    element: StructuralElement,
    label: str,
) -> None:
    try:
        pset_entity = pset.add_pset(model, product=product, name="Pset_EyeSteelAI")
        pset.edit_pset(
            model,
            pset=pset_entity,
            properties={
                "ProfileKey": label,
                "ProfileType": element.profile_type,
                "LengthMm": element.length_mm,
                "MemberType": element.type,
                "PositionX": element.position.x,
                "PositionY": element.position.y,
                "PositionZ": element.position.z,
            },
        )
    except Exception:
        pass


def _validate_spatial_spec(spec: StructuralModelSpec) -> None:
    columns = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]
    if not columns or not beams:
        return
    base_z = _column_base_z(columns)
    top_z = _column_top_z(columns)
    for beam in beams:
        if beam.beam_direction_vector is not None:
            continue
        if abs(float(beam.position.z) - base_z) <= Z_EPS_MM:
            continue
        if beam.position.z + Z_EPS_MM < top_z:
            raise IfcGenerationError(
                f"Beam at z={beam.position.z} mm is below column tops (z={top_z} mm). "
                "Beam IfcLocalPlacement Z must equal height_mm."
            )


def _profile_to_element_fields(profile_name: str) -> tuple[str, list[float], str]:
    try:
        resolved = resolve_profile_key(profile_name)
        return resolved.profile_type, list(resolved.dimensions), resolved.key
    except Exception:
        fallback = resolve_profile_key("HEB200")
        return fallback.profile_type, list(fallback.dimensions), profile_name


def _to_structural_element(independent) -> StructuralElement:
    sx, sy, sz = float(independent.start_x), float(independent.start_y), float(independent.start_z)
    ex, ey, ez = float(independent.end_x), float(independent.end_y), float(independent.end_z)

    profile_type, dims, profile_key = _profile_to_element_fields(independent.profile_name)
    category = independent.category

    if category == "column":
        if abs(sx - ex) > Z_EPS_MM or abs(sy - ey) > Z_EPS_MM:
            raise IfcGenerationError(
                f"Column '{independent.id}' must be vertical (start_x/y must equal end_x/y)"
            )
        length = abs(ez - sz)
        if length <= Z_EPS_MM:
            raise IfcGenerationError(f"Column '{independent.id}' has zero height")
        base_z = min(sz, ez)
        return StructuralElement(
            type="column",
            profile_type=profile_type,  # type: ignore[arg-type]
            profile_key=profile_key,
            dimensions=dims,
            length_mm=length,
            position=Position3D(x=sx, y=sy, z=base_z),
        )

    if category == "slab":
        length_x = abs(ex - sx)
        width_y = abs(ey - sy)
        thickness = abs(ez - sz)
        if length_x <= Z_EPS_MM or width_y <= Z_EPS_MM or thickness <= Z_EPS_MM:
            raise IfcGenerationError(
                f"Slab '{independent.id}' must define non-zero length, width, and thickness"
            )
        top_z = max(sz, ez)
        cx = (sx + ex) / 2.0
        cy = (sy + ey) / 2.0
        return StructuralElement(
            type="slab",
            profile_type="RHS",
            profile_key="CONCRETE_SLAB",
            dimensions=[length_x, width_y, thickness],
            length_mm=thickness,
            position=Position3D(x=cx, y=cy, z=top_z),
        )

    # Beam / brace use pure 3D vector extrusion.
    dx, dy, dz = ex - sx, ey - sy, ez - sz
    length = float((dx**2 + dy**2 + dz**2) ** 0.5)
    if length <= Z_EPS_MM:
        raise IfcGenerationError(f"Member '{independent.id}' has zero span")
    beam_axis = "X" if abs(dx) >= abs(dy) else "Y"
    return StructuralElement(
        type="beam",
        profile_type=profile_type,  # type: ignore[arg-type]
        profile_key=profile_key,
        dimensions=dims,
        length_mm=length,
        beam_axis=beam_axis,  # type: ignore[arg-type]
        beam_direction_vector=[dx / length, dy / length, dz / length],
        position=Position3D(x=sx, y=sy, z=sz),
    )


def _compile_structural_intent_to_spec(intent: StructuralIntentIR) -> StructuralModelSpec:
    elements: list[StructuralElement] = []
    for independent in intent.independent_elements:
        element = _to_structural_element(independent)
        if element.type != "slab":
            element = apply_catalog_to_element(element)
        elements.append(element)
    if not elements:
        raise IfcGenerationError("StructuralIntentIR compilation produced no elements")
    return StructuralModelSpec(elements=elements)


def _effective_count_from_intent(intent: StructuralIntentIR, class_name: str) -> int:
    if class_name == "columns":
        return sum(1 for e in intent.independent_elements if e.category == "column")
    if class_name == "slabs":
        return sum(1 for e in intent.independent_elements if e.category == "slab")
    if class_name == "bracing":
        return sum(
            1
            for e in intent.independent_elements
            if e.category == "brace" or "brace" in e.id.casefold()
        )
    if class_name == "secondary_beams":
        return sum(
            1
            for e in intent.independent_elements
            if "secondary" in e.id.casefold() or "joist" in e.id.casefold() or "floor_" in e.id.casefold()
        )
    if class_name == "primary_beams":
        return sum(
            1
            for e in intent.independent_elements
            if "primary" in e.id.casefold() or "girder" in e.id.casefold()
        )
    return 0


def _validate_intent_numeric_constraints(prompt: str, intent: StructuralIntentIR) -> dict[str, float | int]:
    constraints = _parse_prompt_constraints(prompt)
    if not constraints:
        return constraints
    for class_name in ("columns", "primary_beams", "secondary_beams", "bracing", "slabs"):
        key = f"count_{class_name}"
        if key not in constraints:
            continue
        expected = int(constraints[key])
        actual = _effective_count_from_intent(intent, class_name)
        if actual != expected:
            raise IfcGenerationError(f"Prompt requires {expected} '{class_name}' but IR has {actual}")
    return constraints


def _validate_independent_ir_geometry(intent: StructuralIntentIR, constraints: dict[str, float | int]) -> None:
    deck_top = constraints.get("deck_top_elevation_mm")
    for element in intent.independent_elements:
        if element.category == "beam" and deck_top is not None:
            if abs(float(element.start_z) - float(element.end_z)) > Z_EPS_MM:
                raise IfcGenerationError(
                    f"Flat-deck prompt forbids sloped beam '{element.id}' "
                    f"(start_z={element.start_z}, end_z={element.end_z})"
                )
        if element.category == "slab" and deck_top is not None:
            top_z = max(float(element.start_z), float(element.end_z))
            if abs(top_z - float(deck_top)) > 1.0:
                raise IfcGenerationError(
                    f"Slab '{element.id}' top z={top_z} must match deck_top_elevation_mm={deck_top}"
                )


def _validate_compiled_spec_against_constraints(spec: StructuralModelSpec, constraints: dict[str, float | int]) -> None:
    if not constraints:
        return
    columns = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]
    slabs = [e for e in spec.elements if e.type == "slab"]
    deck_top = constraints.get("deck_top_elevation_mm")

    if "count_columns" in constraints and len(columns) != int(constraints["count_columns"]):
        raise IfcGenerationError(f"Compiled spec has {len(columns)} columns but prompt requires {int(constraints['count_columns'])}")
    if "count_slabs" in constraints and len(slabs) != int(constraints["count_slabs"]):
        raise IfcGenerationError(f"Compiled spec has {len(slabs)} slabs but prompt requires {int(constraints['count_slabs'])}")

    sloped_beams = [
        b
        for b in beams
        if b.beam_direction_vector is not None and abs(float(b.beam_direction_vector[2])) > 0.02
    ]
    if deck_top is not None:
        allowed_sloped = int(constraints.get("count_bracing", 0))
        if len(sloped_beams) > allowed_sloped:
            raise IfcGenerationError(
                f"Flat-deck prompt produced {len(sloped_beams)} sloped beam(s), "
                f"but only {allowed_sloped} knee brace(s) are allowed"
            )

    if "count_secondary_beams" in constraints and deck_top is not None:
        secondary = [
            b
            for b in beams
            if b.beam_direction_vector is not None
            and abs(float(b.beam_direction_vector[2])) <= 0.02
            and abs(float(b.position.z) - float(deck_top)) <= 1.0
        ]
        expected = int(constraints["count_secondary_beams"])
        if len(secondary) != expected:
            raise IfcGenerationError(
                f"Compiled spec has {len(secondary)} deck-level horizontal beams at z={deck_top}, "
                f"but prompt requires exactly {expected}"
            )

    if "count_primary_beams" in constraints:
        col_top = constraints.get("column_top_mm", constraints.get("eave_height_mm"))
        if col_top is not None:
            primary = [
                b
                for b in beams
                if b.beam_direction_vector is not None
                and abs(float(b.beam_direction_vector[2])) <= 0.02
                and abs(float(b.position.z) - float(col_top)) <= 1.0
            ]
            expected = int(constraints["count_primary_beams"])
            if len(primary) != expected:
                raise IfcGenerationError(
                    f"Compiled spec has {len(primary)} primary horizontal beams at z={col_top}, "
                    f"but prompt requires exactly {expected}"
                )

    if "count_bracing" in constraints:
        expected = int(constraints["count_bracing"])
        braces = [
            b
            for b in beams
            if b.beam_direction_vector is not None and abs(float(b.beam_direction_vector[2])) > 0.02
        ]
        if len(braces) != expected:
            raise IfcGenerationError(
                f"Compiled spec has {len(braces)} sloped brace-like beams but prompt requires exactly {expected}"
            )


def _validate_pure_model_geometry(model: PureStructuralModelSpec) -> None:
    for el in model.elements:
        dx = float(el.end_x) - float(el.start_x)
        dy = float(el.end_y) - float(el.start_y)
        dz = float(el.end_z) - float(el.start_z)
        length = (dx * dx + dy * dy + dz * dz) ** 0.5
        if length <= Z_EPS_MM:
            raise IfcGenerationError(f"Pure element '{el.id}' has zero segment length")


def compile_pure_to_spec_with_constraints(
    prompt: str, model: PureStructuralModelSpec
) -> tuple[StructuralModelSpec, dict[str, float | int]]:
    """Compile pure vector model to IFC spec (geometry-only; no semantic member-class checks)."""
    _validate_pure_model_geometry(model)
    try:
        spec = compile_pure_to_spec(model)
    except PureVectorCompileError as exc:
        raise IfcGenerationError(str(exc)) from exc
    return spec, {}


def compile_intent_ir_to_spec_with_constraints(
    prompt: str, intent: StructuralIntentIR
) -> tuple[StructuralModelSpec, dict[str, float | int]]:
    """Legacy semantic IR path; delegates to pure vector compiler."""
    pure = ir_to_pure_model(intent)
    return compile_pure_to_spec_with_constraints(prompt, pure)


def _graph_to_structural_spec(graph: DynamicGraphLayoutRequest) -> StructuralModelSpec:
    """
    Two-pass constraint solver:
    Pass 1: place/extrude columns from grid coordinates.
    Pass 2: place beams from supported_by column top-node references.
    """
    elements: list[StructuralElement] = []
    top_nodes: dict[str, tuple[float, float, float]] = {}

    # Pass 1: columns.
    for data in graph.elements:
        if data.type != "column":
            continue
        assert data.grid_position is not None
        assert data.height_mm is not None
        x = float(data.grid_position.col) * float(graph.span_x_mm)
        y = float(data.grid_position.row) * float(graph.span_y_mm)
        z = 0.0
        resolved = apply_catalog_to_element(
            StructuralElement(
                type="column",
                profile_type="HEB",
                profile_key=data.profile_name,
                dimensions=[200, 200, 9, 15],
                length_mm=float(data.height_mm),
                position=Position3D(x=x, y=y, z=z),
            )
        )
        elements.append(resolved)
        top_nodes[data.id] = (x, y, float(data.height_mm))

    def _representative_beam_node(start: tuple[float, float, float], end: tuple[float, float, float]) -> tuple[float, float, float]:
        # Prefer upper node for members that support roof purlins/chords.
        if end[2] > start[2] + Z_EPS_MM:
            return end
        if start[2] > end[2] + Z_EPS_MM:
            return start
        # Flat members: midpoint is a stable support proxy.
        return ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0, (start[2] + end[2]) / 2.0)

    support_nodes: dict[str, tuple[float, float, float]] = dict(top_nodes)
    support_points: dict[str, list[tuple[float, float, float]]] = {k: [v] for k, v in top_nodes.items()}

    def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        dz = a[2] - b[2]
        return float((dx**2 + dy**2 + dz**2) ** 0.5)

    def _pick_support_pair(beam_id: str, supported_by: list[str]) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        if not supported_by:
            return None
        start_id = supported_by[0]
        end_id = supported_by[-1]
        if start_id not in support_points or end_id not in support_points:
            return None

        # First try preserving ordered endpoint semantics.
        best_pair: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
        best_len = -1.0
        for sp in support_points[start_id]:
            for ep in support_points[end_id]:
                d = _distance(sp, ep)
                if d > best_len:
                    best_len = d
                    best_pair = (sp, ep)
        if best_pair is not None and best_len > Z_EPS_MM:
            return best_pair

        # Fallback: if LLM provided multiple supports, pick the widest valid pair.
        resolved_ids = [sid for sid in supported_by if sid in support_points]
        for i in range(len(resolved_ids)):
            for j in range(i + 1, len(resolved_ids)):
                for sp in support_points[resolved_ids[i]]:
                    for ep in support_points[resolved_ids[j]]:
                        d = _distance(sp, ep)
                        if d > best_len:
                            best_len = d
                            best_pair = (sp, ep)
        if best_pair is not None and best_len > Z_EPS_MM:
            return best_pair

        # Single-support beams can still be resolved if support has two explicit points.
        if len(supported_by) == 1 and start_id in support_points and len(support_points[start_id]) >= 2:
            points = support_points[start_id]
            local_best: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
            local_len = -1.0
            for i in range(len(points)):
                for j in range(i + 1, len(points)):
                    d = _distance(points[i], points[j])
                    if d > local_len:
                        local_len = d
                        local_best = (points[i], points[j])
            if local_best is not None and local_len > Z_EPS_MM:
                return local_best
        return None
    pending_beams = [data for data in graph.elements if data.type == "beam"]
    resolved_any = True
    while pending_beams and resolved_any:
        resolved_any = False
        next_pending: list = []
        for data in pending_beams:
            assert data.supported_by is not None
            start_id = data.supported_by[0]
            end_id = data.supported_by[-1]
            if start_id not in support_points or end_id not in support_points:
                next_pending.append(data)
                continue
            pair = _pick_support_pair(data.id, data.supported_by)
            if pair is None:
                # Do not fail entire model for one malformed member.
                continue
            (sx, sy, sz), (ex, ey, ez) = pair
            dx = ex - sx
            dy = ey - sy
            dz = ez - sz
            true_length = float((dx ** 2 + dy ** 2 + dz ** 2) ** 0.5)
            dir_vector = (dx / true_length, dy / true_length, dz / true_length)
            if not np.isfinite(np.array(dir_vector, dtype=float)).all():
                raise IfcGenerationError(f"Beam '{data.id}' has non-finite direction vector")

            # Keep beam_axis for backwards-compatible metadata; direction controls geometry.
            beam_axis = "X" if abs(dx) >= abs(dy) else "Y"

            resolved = apply_catalog_to_element(
                StructuralElement(
                    type="beam",
                    profile_type="IPE",
                    profile_key=data.profile_name,
                    dimensions=[200, 100, 5.6, 8.5],
                    length_mm=true_length,
                    beam_axis=beam_axis,  # type: ignore[arg-type]
                    beam_direction_vector=[float(dir_vector[0]), float(dir_vector[1]), float(dir_vector[2])],
                    position=Position3D(x=sx, y=sy, z=sz),
                )
            )
            elements.append(resolved)
            support_nodes[data.id] = _representative_beam_node((sx, sy, sz), (ex, ey, ez))
            support_points[data.id] = [
                (sx, sy, sz),
                (ex, ey, ez),
                support_nodes[data.id],
            ]
            resolved_any = True
        pending_beams = next_pending

    if pending_beams:
        # Any unresolved beams were dependent on unknown/unresolvable supports; skip them.
        pass

    if not elements:
        raise IfcGenerationError("Dynamic graph produced no structural elements")
    return StructuralModelSpec(elements=elements)


def generate_ifc_from_spec(spec: StructuralModelSpec) -> bytes:
    """Build an IFC4 model in millimetres from a structured structural specification."""
    if not spec.elements:
        raise IfcGenerationError("StructuralModelSpec must contain at least one element")

    _validate_spatial_spec(spec)

    model = project.create_file("IFC4")
    model_context, storey = _create_spatial_structure(model)

    elements = list(spec.elements)
    products: list[ifcopenshell.entity_instance] = []
    for index, element in enumerate(elements, start=1):
        products.append(
            _add_element(
                model,
                model_context=model_context,
                storey=storey,
                element=element,
                index=index,
                all_elements=elements,
            )
        )

    if not products:
        raise IfcGenerationError("No structural elements were created")

    return _write_model_to_bytes(model)


def generate_ifc_from_graph(graph: DynamicGraphLayoutRequest) -> bytes:
    spec = _graph_to_structural_spec(graph)
    return generate_ifc_from_spec(spec)


def generate_ifc_from_pure_model(prompt: str, model: PureStructuralModelSpec) -> bytes:
    spec, _ = compile_pure_to_spec_with_constraints(prompt, model)
    return generate_ifc_from_spec(spec)


def generate_ifc_from_intent_ir(prompt: str, intent: StructuralIntentIR) -> bytes:
    pure = ir_to_pure_model(intent)
    return generate_ifc_from_pure_model(prompt, pure)

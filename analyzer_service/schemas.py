"""
API and structural specification models for chat-to-IFC.

Structural dimension conventions (millimetres):
- RHS: [width, height, wall_thickness] -> IfcRectangleHollowProfileDef
- IPE / HEB / HEA: [overall_depth, overall_width, web_thickness, flange_thickness] -> IfcIShapeProfileDef

When profile_key is set, catalog resolution overrides dimensions at normalize/generate time.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Chat API ---


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "ai"]
    text: str


class ChatToIfcRequest(BaseModel):
    prompt: str
    history: list[HistoryMessage] = Field(default_factory=list)
    messages: list[HistoryMessage] | None = None

    def resolved_history(self) -> list[HistoryMessage]:
        if self.history:
            return self.history
        if self.messages:
            return self.messages
        return []


# --- Dynamic graph intent (LLM output) ---


class GridPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=0)
    col: int = Field(ge=0)


class IFCElementData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: Literal["column", "beam"]
    profile_name: str = Field(min_length=1)
    height_mm: float | None = Field(default=None, gt=0)
    grid_position: GridPosition | None = None
    supported_by: list[str] | None = None

    @model_validator(mode="after")
    def validate_role_fields(self) -> "IFCElementData":
        if self.type == "column":
            if self.height_mm is None:
                raise ValueError("column requires height_mm")
            if self.grid_position is None:
                raise ValueError("column requires grid_position")
        else:
            if not self.supported_by or len(self.supported_by) < 1:
                raise ValueError("beam requires supported_by with at least one support ID")
        return self


class DynamicGraphLayoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_x_mm: float = Field(gt=0)
    span_y_mm: float = Field(gt=0)
    elements: list[IFCElementData] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "DynamicGraphLayoutRequest":
        ids = [e.id for e in self.elements]
        if len(set(ids)) != len(ids):
            raise ValueError("elements must have unique id values")
        return self

    @classmethod
    def openai_strict_json_schema(cls) -> dict[str, Any]:
        from openai.lib._pydantic import to_strict_json_schema

        return to_strict_json_schema(cls)


# --- Universal grid-frame intent (LLM output; no absolute coordinates) ---

MemberOrientation = Literal[
    "vertical",
    "horizontal_x",
    "horizontal_y",
    "horizontal_y_per_frame",
    "inclined_y",
    "inclined_dual_y",
    "diagonal_plan",
    "truss_web_panels",
    "roof_purlins_dual_slope",
    "wall_girts_fixed_z",
]
GridAssignment = Literal[
    "all_frame_lines",
    "perimeter",
    "along_all_x_at_y_min",
    "along_all_x_at_y_max",
    "along_x_between_columns",
    "along_y_at_frame_ends",
    "along_y_per_frame_line",
    "along_y_per_x_station",
    "distributed_along_x",
    "distributed_along_y",
    "along_y_at_x_min",
    "along_y_at_x_max",
    "along_x_at_y_max",
    "along_x_at_fixed_y",
    "along_y_at_fixed_x",
    "along_x_at_each_y_line",
    "corner_braces",
    "first_and_last_bay_braces",
    "roof_truss_diagonals",
    "per_x_station",
    "full_grid_footprint",
]


class LevelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    elevation_mm: float


class GridFrameSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length_x_mm: float = Field(gt=0)
    width_y_mm: float = Field(gt=0)
    bay_spacing_x_mm: float = Field(gt=0)
    frame_line_x_mm: list[float] | None = Field(
        default=None,
        description="X positions of column grid lines (non-uniform bays); defaults to uniform spacing",
    )
    frame_line_y_mm: list[float] | None = Field(
        default=None,
        description="Y positions of frame lines; defaults to [0, width_y_mm]",
    )


class StructuralGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    orientation: MemberOrientation
    assigned_to_grid: GridAssignment
    start_level: str = Field(min_length=1)
    end_level: str = Field(min_length=1)
    spacing_mm: float | None = Field(default=None, gt=0)
    member_count: int | None = Field(default=None, ge=1)
    brace_offset_x_mm: float | None = Field(default=None, gt=0)
    fixed_elevations_mm: list[float] | None = Field(default=None, min_length=1)
    x_min_mm: float | None = Field(default=None, ge=0)
    x_max_mm: float | None = Field(default=None, ge=0)
    y_from_mm: float | None = Field(default=None, ge=0)
    y_to_mm: float | None = Field(default=None, ge=0)
    y_at_mm: list[float] | None = Field(default=None, min_length=1)
    y_min_mm: float | None = Field(default=None, ge=0)
    y_max_mm: float | None = Field(default=None, ge=0)
    category: Literal["column", "beam", "brace", "slab"] = "beam"

    @model_validator(mode="before")
    @classmethod
    def _normalize_warren_web_assignment(cls, data: Any) -> Any:
        from analyzer_service.geometry_assignments import normalize_structural_group_dict

        if isinstance(data, dict):
            return normalize_structural_group_dict(data)
        return data


class SlabGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    top_level: str = Field(min_length=1)
    thickness_mm: float = Field(gt=0)
    footprint: Literal["full_grid", "partial_xy"] = "full_grid"
    x_min_mm: float | None = Field(default=None, ge=0)
    x_max_mm: float | None = Field(default=None, ge=0)
    y_min_mm: float | None = Field(default=None, ge=0)
    y_max_mm: float | None = Field(default=None, ge=0)


class UniversalStructuralIntent(BaseModel):
    """
    Project-agnostic structural intent.
    Python grid-frame compiler expands this into absolute member coordinates.
    """

    model_config = ConfigDict(extra="forbid")

    levels: list[LevelSpec] = Field(min_length=1)
    grid: GridFrameSpec
    groups: list[StructuralGroupSpec] = Field(min_length=1)
    slabs: list[SlabGroupSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_level_names(self) -> "UniversalStructuralIntent":
        names = [level.name for level in self.levels]
        if len(set(names)) != len(names):
            raise ValueError("levels must have unique names")
        return self

    @classmethod
    def openai_strict_json_schema(cls) -> dict[str, Any]:
        from openai.lib._pydantic import to_strict_json_schema

        return to_strict_json_schema(cls)


# --- Pure vector IR (geometry only; no architectural semantics) ---


class PureSteelElementSpec(BaseModel):
    """
    Primitive steel member: a 3D line segment with a catalog profile.
    The geometry compiler does not interpret roles (column, truss chord, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    start_x: float
    start_y: float
    start_z: float
    end_x: float
    end_y: float
    end_z: float
    up_vector_z: float | None = Field(
        default=1.0,
        description="Local profile up hint (default +Z); controls extrusion twist when not aligned to world Z",
    )

    @model_validator(mode="after")
    def nonzero_segment(self) -> "PureSteelElementSpec":
        if (
            abs(self.start_x - self.end_x) <= 1e-6
            and abs(self.start_y - self.end_y) <= 1e-6
            and abs(self.start_z - self.end_z) <= 1e-6
        ):
            raise ValueError("pure steel element must have non-zero start/end separation")
        return self


class PureSlabBoxSpec(BaseModel):
    """Axis-aligned concrete volume (bounding box only)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def to_bbox_dict(self) -> dict[str, float | str]:
        return {
            "id": self.id,
            "min_x": self.min_x,
            "min_y": self.min_y,
            "min_z": self.min_z,
            "max_x": self.max_x,
            "max_y": self.max_y,
            "max_z": self.max_z,
        }


class PureStructuralModelSpec(BaseModel):
    """
    Pure vector structural model: only line segments and optional concrete boxes.
    """

    model_config = ConfigDict(extra="forbid")

    elements: list[PureSteelElementSpec] = Field(min_length=1)
    slabs: list[PureSlabBoxSpec] | None = Field(
        default=None,
        description="Optional concrete volumes as axis-aligned bounding boxes",
    )

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "PureStructuralModelSpec":
        ids = [e.id for e in self.elements]
        if self.slabs:
            ids.extend(s.id for s in self.slabs)
        if len(set(ids)) != len(ids):
            raise ValueError("element and slab ids must be unique")
        return self

    @classmethod
    def openai_strict_json_schema(cls) -> dict[str, Any]:
        from openai.lib._pydantic import to_strict_json_schema

        return to_strict_json_schema(cls)


# --- Legacy compiled coordinate IR (semantic categories; prefer PureStructuralModelSpec) ---

IndependentCategory = Literal["column", "beam", "slab", "brace"]


class IndependentElementSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: IndependentCategory
    profile_name: str = Field(min_length=1)
    start_x: float
    start_y: float
    start_z: float
    end_x: float
    end_y: float
    end_z: float

    @model_validator(mode="after")
    def nonzero_geometry(self) -> "IndependentElementSpec":
        if (
            abs(self.start_x - self.end_x) <= 1e-6
            and abs(self.start_y - self.end_y) <= 1e-6
            and abs(self.start_z - self.end_z) <= 1e-6
        ):
            raise ValueError("independent element start/end points must define non-zero geometry")
        return self


class StructuralIntentIR(BaseModel):
    """
    Coordinate IR produced by the universal grid-frame compiler.
    Geometry is fully defined by absolute start/end coordinates per member.
    """

    model_config = ConfigDict(extra="forbid")

    independent_elements: list[IndependentElementSpec] = Field(min_length=1)

    @classmethod
    def openai_strict_json_schema(cls) -> dict[str, Any]:
        from openai.lib._pydantic import to_strict_json_schema

        return to_strict_json_schema(cls)


# --- Structural spec (LLM output) ---

ProfileType = Literal["RHS", "HEA", "HEB", "HEM", "IPE", "UPN", "UPE", "L", "CHS"]
ElementType = Literal["column", "beam", "slab"]
BeamAxis = Literal["X", "Y"]


class Position3D(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class StructuralElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ElementType
    profile_type: ProfileType
    profile_key: str | None = Field(
        default=None,
        description="Canonical catalog id, e.g. HEB200, IPE400, 200x200x10",
    )
    dimensions: list[float] = Field(min_length=2, max_length=4)
    length_mm: float = Field(gt=0)
    beam_axis: BeamAxis = Field(
        default="X",
        description="Beam extrusion axis in plan; columns always vertical (+Z)",
    )
    beam_direction_vector: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Optional normalized 3D extrusion direction for graph/inclined beams",
    )
    position: Position3D = Field(default_factory=Position3D)

    @field_validator("dimensions")
    @classmethod
    def dimensions_must_be_positive(cls, values: list[float]) -> list[float]:
        if any(v <= 0 for v in values):
            raise ValueError("all dimensions must be positive (mm)")
        return values

    @field_validator("beam_direction_vector")
    @classmethod
    def validate_beam_direction_vector(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 3:
            raise ValueError("beam_direction_vector must contain 3 values")
        if any(not math.isfinite(v) for v in value):
            raise ValueError("beam_direction_vector must contain finite values")
        magnitude = math.sqrt(value[0] ** 2 + value[1] ** 2 + value[2] ** 2)
        if magnitude <= 0:
            raise ValueError("beam_direction_vector magnitude must be > 0")
        return [value[0] / magnitude, value[1] / magnitude, value[2] / magnitude]

    @model_validator(mode="after")
    def normalize_dimensions(self) -> StructuralElement:
        from analyzer_service.steel_catalog import profile_shape

        dims = list(self.dimensions)
        if self.type == "slab":
            if len(dims) != 3:
                raise ValueError("slab requires 3 dimensions: [length, width, thickness]")
            return self
        shape = profile_shape(self.profile_type)

        if shape == "CHS":
            if len(dims) != 2:
                raise ValueError("CHS requires 2 dimensions: [outer_diameter, wall_thickness]")
            return self
        if shape == "RHS":
            if len(dims) != 3:
                raise ValueError("RHS/SHS requires 3 dimensions: [width, depth, wall_thickness]")
            return self
        if shape == "L":
            if len(dims) != 3:
                raise ValueError("L requires 3 dimensions: [depth, width, thickness]")
            return self

        # I-shape / U-shape: [depth, width, web, flange]; pad flange if omitted.
        if len(dims) == 3:
            depth, width, web = dims
            flange = max(web * 1.5, 8.0)
            self.dimensions = [depth, width, web, flange]
        elif len(dims) != 4:
            raise ValueError(
                "I-shape/U-shape require 3 or 4 dimensions: "
                "[depth, width, web_thickness] or include flange_thickness"
            )
        return self


class StructuralModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elements: list[StructuralElement] = Field(min_length=1)

    @classmethod
    def openai_strict_json_schema(cls) -> dict[str, Any]:
        """JSON schema for OpenAI structured outputs (strict mode)."""
        from openai.lib._pydantic import to_strict_json_schema

        return to_strict_json_schema(cls)


# --- Parametric layout intent (LLM output; no coordinates) ---

LayoutType = Literal["portal_frame", "column_row", "single_element", "steel_shed"]


class ParametricLayoutRequest(BaseModel):
    """
    Structural intent only. Python layout templates compute all 3D positions.

    NOTE: Keep this schema intentionally small and rigid so the LLM cannot
    \"invent\" geometry. All math happens in Python templates.
    """

    model_config = ConfigDict(extra="forbid")

    layout_type: LayoutType
    profile_name: str
    column_profile_name: str | None = Field(
        default=None,
        description="Optional section for columns; falls back to profile_name when null",
    )
    beam_profile_name: str | None = Field(
        default=None,
        description="Optional section for beams; falls back to profile_name when null",
    )
    rafter_profile_name: str | None = Field(
        default=None,
        description="Optional section for shed rafters; falls back to beam_profile_name/profile_name",
    )
    purlin_profile_name: str | None = Field(
        default=None,
        description="Optional section for shed purlins; falls back to beam_profile_name/profile_name",
    )
    base_beam_profile_name: str | None = Field(
        default=None,
        description="Optional section for shed perimeter/base beams; falls back to beam_profile_name/profile_name",
    )
    height_mm: float = Field(default=3000.0, gt=0)
    total_length_mm: float = Field(default=5000.0, gt=0)
    width_mm: float = Field(default=4000.0, gt=0)
    column_count: int = Field(default=2, ge=2, le=50)
    purlin_count: int = Field(default=4, ge=1, le=50)

    @model_validator(mode="after")
    def normalize_profile_name(self) -> "ParametricLayoutRequest":
        from analyzer_service.steel_catalog import normalize_profile_name

        normalized = normalize_profile_name(self.profile_name)
        if normalized:
            self.profile_name = normalized

        col = normalize_profile_name(self.column_profile_name)
        if col:
            self.column_profile_name = col
        beam = normalize_profile_name(self.beam_profile_name)
        if beam:
            self.beam_profile_name = beam
        rafter = normalize_profile_name(self.rafter_profile_name)
        if rafter:
            self.rafter_profile_name = rafter
        purlin = normalize_profile_name(self.purlin_profile_name)
        if purlin:
            self.purlin_profile_name = purlin
        base = normalize_profile_name(self.base_beam_profile_name)
        if base:
            self.base_beam_profile_name = base
        return self

    def resolved_column_profile(self) -> str:
        return self.column_profile_name or self.profile_name

    def resolved_beam_profile(self) -> str:
        return self.beam_profile_name or self.profile_name

    def resolved_rafter_profile(self) -> str:
        return self.rafter_profile_name or self.beam_profile_name or self.profile_name

    def resolved_purlin_profile(self) -> str:
        return self.purlin_profile_name or self.beam_profile_name or self.profile_name

    def resolved_base_beam_profile(self) -> str:
        return self.base_beam_profile_name or self.beam_profile_name or self.profile_name

    @classmethod
    def openai_strict_json_schema(cls) -> dict[str, Any]:
        from openai.lib._pydantic import to_strict_json_schema

        return to_strict_json_schema(cls)

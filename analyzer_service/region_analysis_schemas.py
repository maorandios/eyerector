"""Schemas for PDF region crop → vision analysis → grid-frame compile."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ElementType = Literal["grid", "truss", "mezzanine", "staircase", "unknown"]
LayoutMode = Literal["dense_matrix", "sparse_intersections"]

JsonValue = str | int | float | bool | list[str]


class DetectedParameterEntry(BaseModel):
    """Strict-schema-safe key/value pair (OpenAI rejects open dict types)."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    value: str = Field(
        min_length=1,
        description="Metric as plain number or text without units, e.g. 12000 or HEB200",
    )


class PageAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(ge=1)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    url: str = Field(min_length=1)


class UploadPdfResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    filename: str
    page_count: int = Field(ge=1)
    base_url: str = Field(min_length=1)
    pages: list[PageAsset] = Field(min_length=1)


class ColumnPlacement(BaseModel):
    """Exact column position from plan dimensions (mm, global origin at crop grid min corner)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    x_mm: float
    y_mm: float
    profile_name: str = Field(default="HEB200", min_length=1)
    height_mm: float = Field(default=6000.0, gt=0)
    mark: str | None = Field(default=None, description="Plan column mark e.g. C1, C14")


class ActiveColumnIntersection(BaseModel):
    """Sparse column at a grid crossing, addressed by 0-based indices into x/y station arrays."""

    model_config = ConfigDict(extra="forbid")

    grid_index_x: int = Field(ge=0, description="0-based index into x_grid_positions_mm")
    grid_index_y: int = Field(ge=0, description="0-based index into y_grid_positions_mm")
    mark: str | None = Field(default=None, description="Plan label when visible e.g. C1")
    profile_name: str | None = Field(
        default=None,
        description="Per-column section override; null if default column_profile applies",
    )


class ColumnMarkProfile(BaseModel):
    """Legend mapping from column mark to catalog profile name."""

    model_config = ConfigDict(extra="forbid")

    mark: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)


class CropRectNorm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class RegionStructuralAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_type: ElementType
    confidence: float = Field(ge=0, le=1)
    detected_parameters: list[DetectedParameterEntry] = Field(default_factory=list)
    x_grid_positions_mm: list[float] = Field(
        default_factory=list,
        max_length=64,
        description="Cumulative X grid line positions from dimension chains (include 0)",
    )
    y_grid_positions_mm: list[float] = Field(
        default_factory=list,
        max_length=64,
        description="Cumulative Y grid line positions from dimension chains (include 0)",
    )
    x_bay_spacings_mm: list[float] = Field(
        default_factory=list,
        max_length=64,
        description="Ordered bay widths along X left-to-right (not cumulative)",
    )
    y_bay_spacings_mm: list[float] = Field(
        default_factory=list,
        max_length=64,
        description="Ordered bay widths along Y bottom-to-top (not cumulative)",
    )
    column_placements: list[ColumnPlacement] = Field(
        default_factory=list,
        max_length=200,
        description="Full explicit column list when vision emits every column with id/profile",
    )
    layout_mode: LayoutMode = Field(
        default="dense_matrix",
        description="dense_matrix = all grid crossings; sparse_intersections = active_column_intersections only",
    )
    active_column_intersections: list[ActiveColumnIntersection] = Field(
        default_factory=list,
        max_length=400,
        description="When non-empty or layout_mode sparse, place columns only at these grid indices",
    )
    column_profile_by_mark: list[ColumnMarkProfile] = Field(
        default_factory=list,
        max_length=64,
        description="Legend mapping from column mark to section name",
    )
    notes: str | None = None

    def parameters_dict(self) -> dict[str, JsonValue]:
        """Flatten list entries for grid_frame mapper and UI overrides."""
        out: dict[str, JsonValue] = {}
        for entry in self.detected_parameters:
            raw = entry.value.strip()
            if raw.lower() in ("true", "false"):
                out[entry.key] = raw.lower() == "true"
                continue
            cleaned = raw.replace(",", "")
            try:
                out[entry.key] = float(cleaned) if "." in cleaned else int(cleaned)
            except ValueError:
                if "," in raw:
                    out[entry.key] = [s.strip() for s in raw.split(",") if s.strip()]
                else:
                    out[entry.key] = raw
        return out

    @classmethod
    def openai_strict_json_schema(cls) -> dict[str, Any]:
        from openai.lib._pydantic import to_strict_json_schema

        return to_strict_json_schema(cls)


class PdfGridMeta(BaseModel):
    """Status of PDF dimension/grid extraction for plan-crop (visible in UI)."""

    model_config = ConfigDict(extra="forbid")

    attempted: bool = False
    applied: bool = False
    source: str = "none"
    confidence: float = Field(default=0.0, ge=0, le=1)
    x_line_count: int = Field(default=0, ge=0)
    y_line_count: int = Field(default=0, ge=0)
    error: str | None = None
    detail: str | None = None


class GridVertexDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_index_x: int = Field(ge=0)
    grid_index_y: int = Field(ge=0)
    x_px: float
    y_px: float


class RegionGridGeometryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    page_index: int = Field(ge=0)
    crop_rect_norm: CropRectNorm
    scale_note: str | None = None


class RegionGridGeometryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crop_width_px: int = Field(gt=0)
    crop_height_px: int = Field(gt=0)
    x_lines_px: list[float] = Field(default_factory=list)
    y_lines_px: list[float] = Field(default_factory=list)
    vertices: list[GridVertexDTO] = Field(default_factory=list)
    svg_markup: str = ""
    mm_per_px: float | None = None
    span_width_mm: float | None = None
    span_height_mm: float | None = None
    source: str = "none"
    notes: list[str] = Field(default_factory=list)
    ok: bool = True
    error: str | None = None


class RegionGridFinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry: RegionGridGeometryResponse
    intersections: list[ActiveColumnIntersection] = Field(default_factory=list)
    column_profile: str = "HEB200"
    column_height_mm: float = Field(default=6000.0, gt=0)
    parameter_overrides: dict[str, JsonValue] | None = None


class ColumnClickDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_norm: float | None = Field(default=None, ge=0, le=1)
    y_norm: float | None = Field(default=None, ge=0, le=1)
    x_pt: float | None = None
    y_pt: float | None = None
    x_px: float = Field(ge=0)
    y_px: float = Field(ge=0)
    mark: str | None = None


class RegionCropCalibrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    page_index: int = Field(ge=0)
    crop_rect_norm: CropRectNorm
    scale_note: str | None = None


class CropBoundsPtDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x0: float
    y0: float
    x1: float
    y1: float


class RegionCropCalibrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crop_width_px: int = Field(gt=0)
    crop_height_px: int = Field(gt=0)
    mm_per_px: float | None = None
    mm_per_px_x: float | None = None
    mm_per_px_y: float | None = None
    span_width_mm: float | None = None
    span_height_mm: float | None = None
    x_grid_positions_mm: list[float] = Field(default_factory=list)
    y_grid_positions_mm: list[float] = Field(default_factory=list)
    grid_lines_x_px: list[float] = Field(default_factory=list)
    grid_lines_y_px: list[float] = Field(default_factory=list)
    grid_lines_x_pt: list[float] = Field(default_factory=list)
    grid_lines_y_pt: list[float] = Field(default_factory=list)
    crop_bounds_pt: CropBoundsPtDTO | None = None
    vector_grid_source: str = "none"
    suggested_column_profile: str | None = None
    notes: list[str] = Field(default_factory=list)


class ColumnPinDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    x_norm: float = Field(ge=0, le=1)
    y_norm: float = Field(ge=0, le=1)
    x_pt: float | None = None
    y_pt: float | None = None
    mark: str | None = None


class AlignPinsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pins: list[ColumnPinDTO] = Field(min_length=1)
    grid_lines_x_pt: list[float] = Field(min_length=1)
    grid_lines_y_pt: list[float] = Field(min_length=1)
    crop_bounds_pt: CropBoundsPtDTO


class AlignedPinDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    x_norm: float
    y_norm: float
    x_pt: float
    y_pt: float
    snapped_x_pt: float
    snapped_y_pt: float
    grid_index_x: int = Field(ge=0)
    grid_index_y: int = Field(ge=0)
    mark: str | None = None


class AlignPinsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aligned: list[AlignedPinDTO]
    grid_lines_x_pt: list[float]
    grid_lines_y_pt: list[float]


class RegionColumnClicksFinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    page_index: int | None = None
    crop_rect_norm: CropRectNorm | None = None
    crop_width_px: int = Field(gt=0)
    crop_height_px: int = Field(gt=0)
    clicks: list[ColumnClickDTO] = Field(min_length=1)
    mm_per_px: float | None = None
    span_width_mm: float | None = None
    span_height_mm: float | None = None
    x_grid_positions_mm: list[float] = Field(default_factory=list)
    y_grid_positions_mm: list[float] = Field(default_factory=list)
    grid_lines_x_pt: list[float] = Field(default_factory=list)
    grid_lines_y_pt: list[float] = Field(default_factory=list)
    grid_lines_x_px: list[float] = Field(default_factory=list)
    grid_lines_y_px: list[float] = Field(default_factory=list)
    crop_bounds_pt: CropBoundsPtDTO | None = None
    column_profile: str = "HEB200"
    column_height_mm: float = Field(default=6000.0, gt=0)
    parameter_overrides: dict[str, JsonValue] | None = None


class GridAxisDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines_px: list[float] = Field(default_factory=list)
    stations_mm: list[float] = Field(default_factory=list)
    bays_mm: list[float] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class GridColumnDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    mark: str
    x_px: float = Field(ge=0)
    y_px: float = Field(ge=0)
    x_mm: float
    y_mm: float
    grid_ix: int = Field(ge=0)
    grid_iy: int = Field(ge=0)
    source: str = "detected"
    confidence: float = Field(default=0.5, ge=0, le=1)


class GridModelDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crop_width_px: int = Field(gt=0)
    crop_height_px: int = Field(gt=0)
    mm_per_px_x: float = Field(gt=0)
    mm_per_px_y: float = Field(gt=0)
    span_width_mm: float = Field(gt=0)
    span_height_mm: float = Field(gt=0)
    axis_x: GridAxisDTO
    axis_y: GridAxisDTO
    columns: list[GridColumnDTO] = Field(default_factory=list)
    suggested_column_profile: str | None = None
    notes: list[str] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)


class GridModelExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    page_index: int = Field(ge=0)
    crop_rect_norm: CropRectNorm
    scale_note: str | None = None


class GridModelFinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_model: GridModelDTO
    column_profile: str = "HEB200"
    column_height_mm: float = Field(default=6000.0, gt=0)
    parameter_overrides: dict[str, JsonValue] | None = None


class AnalyzeRegionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: RegionStructuralAnalysis
    compile_supported: bool
    compile_message: str | None = None
    ai_model: str | None = None
    pdf_grid: PdfGridMeta | None = None
    vision_raw: dict[str, Any] | None = Field(
        default=None,
        description="RegionStructuralAnalysis JSON from GPT before server-side enrich",
    )


class RegionToIntentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: RegionStructuralAnalysis
    parameter_overrides: dict[str, JsonValue] | None = None


class RegionToIntentPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compile_mode: Literal["explicit_layout", "uniform_grid"] = "uniform_grid"
    intent: dict[str, Any] = Field(default_factory=dict)
    pure_preview: dict[str, Any] | None = None
    column_count: int = 0
    compile_supported: bool
    compile_message: str | None = None

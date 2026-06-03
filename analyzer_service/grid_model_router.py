"""GridModel extract + finish API."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from analyzer_service.grid_model import (
    analysis_from_grid_model,
    extract_grid_model,
    grid_model_from_payload,
)
from analyzer_service.region_analysis_schemas import (
    AnalyzeRegionResponse,
    DetectedParameterEntry,
    GridModelDTO,
    GridModelExtractRequest,
    GridModelFinishRequest,
)
from analyzer_service.region_crop_router import _analyze_response_from_grid_analysis
from analyzer_service.region_layout_compiler import enrich_region_grid_analysis

router = APIRouter()


def _dto_to_dict(dto: GridModelDTO) -> dict:
    return dto.model_dump()


@router.post("/api/grid-model/extract", response_model=GridModelDTO)
async def grid_model_extract(body: GridModelExtractRequest) -> GridModelDTO:
    try:
        model = await asyncio.to_thread(
            extract_grid_model,
            body.project_id,
            body.page_index,
            body.crop_rect_norm,
            scale_note=body.scale_note,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Grid extract failed: {exc}") from exc

    return GridModelDTO.model_validate(model.to_dict())


@router.post("/api/grid-model/finish", response_model=AnalyzeRegionResponse)
async def grid_model_finish(body: GridModelFinishRequest) -> AnalyzeRegionResponse:
    profile = (body.column_profile or "HEB200").strip() or "HEB200"
    try:
        model = grid_model_from_payload(_dto_to_dict(body.grid_model))
        analysis = await asyncio.to_thread(
            analysis_from_grid_model,
            model,
            column_profile=profile,
            height_mm=body.column_height_mm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if body.parameter_overrides:
        for key, val in body.parameter_overrides.items():
            if val is None:
                continue
            existing = next(
                (p for p in analysis.detected_parameters if p.key == key),
                None,
            )
            if existing:
                existing.value = str(val)
            else:
                analysis.detected_parameters.append(
                    DetectedParameterEntry(key=key, value=str(val))
                )

    analysis = enrich_region_grid_analysis(analysis)
    note = "GridModel editor → explicit placements (vector grid + PDF dims)."
    return _analyze_response_from_grid_analysis(analysis, note=note).model_copy(
        update={"ai_model": "grid_model"}
    )

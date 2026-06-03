from __future__ import annotations

import asyncio
import io
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from analyzer_service.ifc_generator import (
    IfcGenerationError,
    compile_pure_to_spec_with_constraints,
    generate_ifc_from_spec,
)
from analyzer_service.llm_extractor import LlmExtractionError
from analyzer_service.pure_vector_compiler import (
    GridFrameCompileError,
    PureVectorCompileError,
    compile_universal_intent_to_pure_model,
)
from analyzer_service.region_analysis_schemas import (
    AnalyzeRegionResponse,
    DetectedParameterEntry,
    PdfGridMeta,
    RegionColumnClicksFinishRequest,
    AlignPinsRequest,
    AlignPinsResponse,
    AlignedPinDTO,
    RegionCropCalibrationRequest,
    RegionCropCalibrationResponse,
    RegionGridFinishRequest,
    RegionGridGeometryRequest,
    RegionGridGeometryResponse,
    RegionStructuralAnalysis,
    RegionToIntentPreviewRequest,
    RegionToIntentPreviewResponse,
    UploadPdfResponse,
)
from analyzer_service.region_column_clicks import (
    analysis_from_column_clicks,
    ColumnClick,
    crop_calibration,
)
from analyzer_service.vector_grid_extractor import (
    align_columns_to_vector_grid,
    CropBoundsPt,
    UserPin,
)
from analyzer_service.region_grid_geometry import (
    extract_region_grid_geometry,
    geometry_from_response,
    geometry_to_response,
    intersections_to_analysis,
)
from analyzer_service.region_intent_mapper import (
    UnsupportedElementError,
    compile_supported_for_type,
    map_region_analysis_to_intent,
)
from analyzer_service.region_layout_compiler import (
    enrich_region_grid_analysis,
    map_region_analysis_to_pure_model,
    resolve_column_placements,
    uses_explicit_layout,
)
from analyzer_service.region_pdf_grid import (
    extract_region_grid_from_pdf,
    merge_pdf_grid_into_analysis,
    parse_crop_rect_norm,
)
from analyzer_service.region_vision import analyze_region_image
from analyzer_service.pdf_project_storage import create_project_from_pdf, save_crop_png
from analyzer_service.schemas import UniversalStructuralIntent

router = APIRouter()


async def _read_pdf_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty PDF upload")
    return data, filename


@router.post("/upload-pdf", response_model=UploadPdfResponse)
async def upload_pdf(file: UploadFile = File(...)) -> UploadPdfResponse:
    """Upload PDF, render pages to PNG, return project manifest."""
    data, filename = await _read_pdf_upload(file)
    try:
        return await asyncio.to_thread(create_project_from_pdf, data, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF project creation failed: {exc}") from exc
    finally:
        await file.close()


@router.post("/analyze-region", response_model=AnalyzeRegionResponse)
async def analyze_region(
    image: UploadFile | None = File(default=None),
    image_base64: str | None = Form(default=None),
    project_id: str | None = Form(default=None),
    page_index: int | None = Form(default=None),
    crop_rect_norm: str | None = Form(default=None),
    scale_note: str | None = Form(default=None),
) -> AnalyzeRegionResponse:
    """Analyze a cropped plan region with vision → structured parameters."""
    png_bytes: bytes | None = None
    if image is not None:
        png_bytes = await image.read()
        await image.close()
    elif image_base64:
        import base64

        raw = image_base64.strip()
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            png_bytes = base64.standard_b64decode(raw)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid image_base64") from exc

    if not png_bytes:
        raise HTTPException(status_code=400, detail="image or image_base64 is required")

    if project_id:
        crop_id = uuid.uuid4().hex[:12]
        try:
            await asyncio.to_thread(save_crop_png, project_id, crop_id, png_bytes)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    try:
        analysis, model_name, vision_raw = await asyncio.to_thread(
            analyze_region_image,
            png_bytes,
            scale_note=scale_note,
        )
    except LlmExtractionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    pdf_meta = PdfGridMeta(attempted=False, applied=False)
    pdf_grid_note: str | None = None
    if project_id and page_index is not None:
        crop = parse_crop_rect_norm(crop_rect_norm)
        if crop is None:
            pdf_meta = PdfGridMeta(
                attempted=True,
                error="invalid_crop_rect_norm",
                detail="crop_rect_norm JSON could not be parsed",
            )
        else:
            pdf_meta = PdfGridMeta(attempted=True)
            try:
                page_idx = int(page_index)
                pdf_grid = await asyncio.to_thread(
                    extract_region_grid_from_pdf,
                    project_id,
                    page_idx,
                    crop,
                    scale_note=scale_note,
                )
                if pdf_grid is None:
                    pdf_meta.error = "source_pdf_missing"
                    pdf_meta.detail = f"No source.pdf for project {project_id}"
                else:
                    pdf_meta.source = pdf_grid.source
                    pdf_meta.confidence = pdf_grid.confidence
                    pdf_meta.x_line_count = len(pdf_grid.x_stations_mm)
                    pdf_meta.y_line_count = len(pdf_grid.y_stations_mm)
                    pdf_meta.detail = "; ".join(pdf_grid.notes) if pdf_grid.notes else None
                    before_x = len(analysis.x_grid_positions_mm)
                    before_y = len(analysis.y_grid_positions_mm)
                    merged = merge_pdf_grid_into_analysis(analysis, pdf_grid)
                    after_x = len(merged.x_grid_positions_mm)
                    after_y = len(merged.y_grid_positions_mm)
                    if after_x > before_x or after_y > before_y or (
                        pdf_grid.confidence >= 0.35
                        and (after_x >= 2 or after_y >= 2)
                    ):
                        analysis = merged
                        pdf_meta.applied = True
                        model_name = f"{model_name}+pdf_grid"
                        pdf_grid_note = pdf_meta.detail
            except FileNotFoundError as exc:
                pdf_meta.error = "project_not_found"
                pdf_meta.detail = str(exc)
            except Exception as exc:
                pdf_meta.error = "pdf_grid_failed"
                pdf_meta.detail = str(exc)

    if analysis.element_type == "grid":
        analysis = enrich_region_grid_analysis(analysis)

    supported = compile_supported_for_type(analysis.element_type)
    message = None
    if analysis.element_type == "grid" and (
        uses_explicit_layout(analysis) or resolve_column_placements(analysis)
    ):
        supported = True
        n_cols = len(resolve_column_placements(analysis))
        message = (
            f"Explicit layout: {n_cols} columns at plan grid positions (non-uniform bays supported)."
        )
        if pdf_grid_note:
            message = f"{message} {pdf_grid_note}"
    elif not supported:
        if analysis.element_type == "staircase":
            message = (
                "Staircase detected but 3D compilation is not available yet. "
                "Adjust the crop or use AI Designer."
            )
        elif analysis.element_type == "unknown":
            message = analysis.notes or "Region type unknown — try a clearer crop."
        else:
            message = f"Compilation not supported for type: {analysis.element_type}"

    return AnalyzeRegionResponse(
        analysis=analysis,
        compile_supported=supported,
        compile_message=message,
        ai_model=model_name,
        pdf_grid=pdf_meta if pdf_meta.attempted else None,
        vision_raw=vision_raw,
    )


def _analyze_response_from_grid_analysis(
    analysis: RegionStructuralAnalysis,
    *,
    note: str | None = None,
) -> AnalyzeRegionResponse:
    analysis = enrich_region_grid_analysis(analysis)
    supported = compile_supported_for_type(analysis.element_type)
    message = note
    if analysis.element_type == "grid" and (
        uses_explicit_layout(analysis) or resolve_column_placements(analysis)
    ):
        supported = True
        n_cols = len(resolve_column_placements(analysis))
        message = (
            f"Explicit layout: {n_cols} columns at grid vertices (SVG snap editor)."
        )
        if note:
            message = f"{message} {note}"
    elif not supported:
        message = message or f"Compilation not supported for type: {analysis.element_type}"
    return AnalyzeRegionResponse(
        analysis=analysis,
        compile_supported=supported,
        compile_message=message,
        ai_model="pdf_grid_geometry",
        pdf_grid=None,
        vision_raw=None,
    )


@router.post("/api/region-grid-geometry", response_model=RegionGridGeometryResponse)
async def region_grid_geometry(body: RegionGridGeometryRequest) -> RegionGridGeometryResponse:
    """Extract grid lines and vertices from PDF vectors in the crop (pixel space)."""
    try:
        geom = await asyncio.to_thread(
            extract_region_grid_geometry,
            body.project_id,
            body.page_index,
            body.crop_rect_norm,
            scale_note=body.scale_note,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Grid geometry failed: {exc}") from exc

    if geom is None:
        return RegionGridGeometryResponse(
            crop_width_px=1,
            crop_height_px=1,
            ok=False,
            error="source_pdf_missing",
            notes=["No source.pdf for this project."],
        )
    payload = geometry_to_response(geom)
    return RegionGridGeometryResponse.model_validate(payload)


@router.post("/api/region-grid-finish", response_model=AnalyzeRegionResponse)
async def region_grid_finish(body: RegionGridFinishRequest) -> AnalyzeRegionResponse:
    """Build compile-ready analysis from snap-editor intersections (no vision)."""
    if not body.geometry.ok:
        raise HTTPException(
            status_code=422,
            detail=body.geometry.error or "Grid geometry was not extracted successfully",
        )
    if not body.intersections:
        raise HTTPException(status_code=422, detail="Select at least one grid vertex (column).")

    geom = geometry_from_response(body.geometry)
    analysis = intersections_to_analysis(
        geom,
        body.intersections,
        column_profile=body.column_profile,
        height_mm=body.column_height_mm,
    )
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
                from analyzer_service.region_analysis_schemas import DetectedParameterEntry

                analysis.detected_parameters.append(
                    DetectedParameterEntry(key=key, value=str(val))
                )
    return _analyze_response_from_grid_analysis(analysis)


@router.post("/api/region-crop-calibration", response_model=RegionCropCalibrationResponse)
async def region_crop_calibration(
    body: RegionCropCalibrationRequest,
) -> RegionCropCalibrationResponse:
    """PDF dimension scan → mm/px scale for column-click workflow (no grid mesh)."""
    try:
        payload = await asyncio.to_thread(
            crop_calibration,
            body.project_id,
            body.page_index,
            body.crop_rect_norm,
            scale_note=body.scale_note,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Calibration failed: {exc}") from exc
    return RegionCropCalibrationResponse.model_validate(payload)


@router.post("/api/vector-grid-extract", response_model=RegionCropCalibrationResponse)
async def vector_grid_extract(body: RegionCropCalibrationRequest) -> RegionCropCalibrationResponse:
    """pdfplumber vector lines in crop + dimension calibration metadata."""
    return await region_crop_calibration(body)


@router.post("/api/align-pins", response_model=AlignPinsResponse)
async def align_pins(body: AlignPinsRequest) -> AlignPinsResponse:
    """Snap column pins to closest pdfplumber grid lines (PDF points)."""
    bounds = CropBoundsPt(
        x0=body.crop_bounds_pt.x0,
        y0=body.crop_bounds_pt.y0,
        x1=body.crop_bounds_pt.x1,
        y1=body.crop_bounds_pt.y1,
    )
    pins = [
        UserPin(
            id=p.id,
            x_norm=p.x_norm,
            y_norm=p.y_norm,
            x_pt=p.x_pt,
            y_pt=p.y_pt,
            mark=p.mark,
        )
        for p in body.pins
    ]
    try:
        aligned = await asyncio.to_thread(
            align_columns_to_vector_grid,
            pins,
            body.grid_lines_x_pt,
            body.grid_lines_y_pt,
            crop_bounds=bounds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return AlignPinsResponse(
        aligned=[
            AlignedPinDTO(
                id=a.id,
                x_norm=a.x_norm,
                y_norm=a.y_norm,
                x_pt=a.x_pt,
                y_pt=a.y_pt,
                snapped_x_pt=a.snapped_x_pt,
                snapped_y_pt=a.snapped_y_pt,
                grid_index_x=a.grid_index_x,
                grid_index_y=a.grid_index_y,
                mark=a.mark,
            )
            for a in aligned
        ],
        grid_lines_x_pt=body.grid_lines_x_pt,
        grid_lines_y_pt=body.grid_lines_y_pt,
    )


@router.post("/api/region-column-clicks-finish", response_model=AnalyzeRegionResponse)
async def region_column_clicks_finish(
    body: RegionColumnClicksFinishRequest,
) -> AnalyzeRegionResponse:
    """Build grid stations from user column clicks + PDF real dimensions."""
    profile = (body.column_profile or "HEB200").strip() or "HEB200"
    if body.project_id and body.page_index is not None and body.crop_rect_norm:
        cal = await asyncio.to_thread(
            crop_calibration,
            body.project_id,
            body.page_index,
            body.crop_rect_norm,
        )
        if cal.get("suggested_column_profile") and profile.upper() in (
            "HEB200",
            "HEA200",
            "IPE200",
        ):
            profile = str(cal["suggested_column_profile"])
        if not body.x_grid_positions_mm and cal.get("x_grid_positions_mm"):
            body = body.model_copy(
                update={
                    "x_grid_positions_mm": cal["x_grid_positions_mm"],
                    "y_grid_positions_mm": cal.get("y_grid_positions_mm") or [],
                    "mm_per_px": body.mm_per_px or cal.get("mm_per_px"),
                    "span_width_mm": body.span_width_mm or cal.get("span_width_mm"),
                    "column_profile": profile,
                }
            )

    try:
        clicks = []
        for i, c in enumerate(body.clicks):
            x_norm = c.x_norm
            y_norm = c.y_norm
            if x_norm is None or y_norm is None:
                w = max(body.crop_width_px, 1)
                h = max(body.crop_height_px, 1)
                x_norm = c.x_px / w
                y_norm = c.y_px / h
            clicks.append(
                ColumnClick(
                    x_px=c.x_px,
                    y_px=c.y_px,
                    x_norm=x_norm,
                    y_norm=y_norm,
                    x_pt=c.x_pt,
                    y_pt=c.y_pt,
                    mark=c.mark,
                    id=f"pin_{i}",
                )
            )
        bounds_dict = None
        if body.crop_bounds_pt:
            bounds_dict = body.crop_bounds_pt.model_dump()

        if body.project_id and body.page_index is not None and body.crop_rect_norm:
            from analyzer_service.region_column_clicks import _build_aligned_grid_px

            cw, ch = body.crop_width_px, body.crop_height_px
            xs0 = list(body.x_grid_positions_mm or [])
            ys0 = list(body.y_grid_positions_mm or [])
            x_px, y_px, xs0, ys0, mm_x, mm_y, _ = await asyncio.to_thread(
                _build_aligned_grid_px,
                body.project_id,
                body.page_index,
                body.crop_rect_norm,
                cw,
                ch,
                xs0,
                ys0,
                click_x_px=[c.x_px for c in body.clicks],
                click_y_px=[c.y_px for c in body.clicks],
            )
            if x_px and y_px and len(xs0) == len(x_px):
                body = body.model_copy(
                    update={
                        "grid_lines_x_px": x_px,
                        "grid_lines_y_px": y_px,
                        "x_grid_positions_mm": xs0,
                        "y_grid_positions_mm": ys0,
                        "mm_per_px": mm_x or body.mm_per_px,
                    }
                )

        analysis = await asyncio.to_thread(
            analysis_from_column_clicks,
            clicks,
            crop_width_px=body.crop_width_px,
            crop_height_px=body.crop_height_px,
            mm_per_px=body.mm_per_px,
            span_width_mm=body.span_width_mm,
            span_height_mm=body.span_height_mm,
            x_grid_positions_mm=body.x_grid_positions_mm,
            y_grid_positions_mm=body.y_grid_positions_mm,
            grid_lines_x_pt=body.grid_lines_x_pt,
            grid_lines_y_pt=body.grid_lines_y_pt,
            grid_lines_x_px=body.grid_lines_x_px,
            grid_lines_y_px=body.grid_lines_y_px,
            crop_bounds_pt=bounds_dict,
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
    note = "Column clicks → grid stations calibrated from PDF dimensions."
    resp = _analyze_response_from_grid_analysis(analysis, note=note)
    return resp.model_copy(update={"ai_model": "column_clicks_pdf"})


@router.post("/api/region-to-intent-preview", response_model=RegionToIntentPreviewResponse)
async def region_to_intent_preview(
    body: RegionToIntentPreviewRequest,
) -> RegionToIntentPreviewResponse:
    try:
        pure = await asyncio.to_thread(
            map_region_analysis_to_pure_model,
            body.analysis,
            body.parameter_overrides,
        )
        if pure is not None:
            return RegionToIntentPreviewResponse(
                compile_mode="explicit_layout",
                intent={},
                pure_preview=pure.model_dump(),
                column_count=len(pure.elements),
                compile_supported=True,
                compile_message=None,
            )
        intent = await asyncio.to_thread(
            map_region_analysis_to_intent,
            body.analysis,
            body.parameter_overrides,
        )
        return RegionToIntentPreviewResponse(
            compile_mode="uniform_grid",
            intent=intent.model_dump(),
            pure_preview=None,
            column_count=0,
            compile_supported=True,
            compile_message=None,
        )
    except UnsupportedElementError as exc:
        return RegionToIntentPreviewResponse(
            compile_mode="uniform_grid",
            intent={},
            compile_supported=False,
            compile_message=str(exc),
        )


@router.post("/api/region-compile-ifc")
async def region_compile_ifc(body: RegionToIntentPreviewRequest) -> StreamingResponse:
    """Compile region analysis (explicit coordinates or uniform grid) → IFC."""
    try:
        pure = await asyncio.to_thread(
            map_region_analysis_to_pure_model,
            body.analysis,
            body.parameter_overrides,
        )
        if pure is not None:
            spec, constraints = await asyncio.to_thread(
                compile_pure_to_spec_with_constraints,
                "",
                pure,
            )
            ifc_bytes = await asyncio.to_thread(generate_ifc_from_spec, spec)
            segment_count = len(pure.elements)
            intent_summary = (
                f"region_crop;mode=explicit_layout;columns={segment_count};"
                f"constraints={','.join(sorted(constraints.keys())) or 'geometry_only'}"
            )
        else:
            intent = await asyncio.to_thread(
                map_region_analysis_to_intent,
                body.analysis,
                body.parameter_overrides,
            )
            pure_model = await asyncio.to_thread(compile_universal_intent_to_pure_model, intent)
            spec, constraints = await asyncio.to_thread(
                compile_pure_to_spec_with_constraints,
                "",
                pure_model,
            )
            ifc_bytes = await asyncio.to_thread(generate_ifc_from_spec, spec)
            segment_count = len(pure_model.elements)
            intent_summary = f"region_crop;mode=uniform_grid;segments={segment_count}"
    except (UnsupportedElementError, GridFrameCompileError, PureVectorCompileError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IfcGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"IFC generation failed: {exc}") from exc

    if not ifc_bytes:
        raise HTTPException(status_code=500, detail="IFC generation returned empty output")

    return StreamingResponse(
        io.BytesIO(ifc_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="region-crop.ifc"',
            "X-Eyesteel-Spec": f"region crop · columns/segments[{segment_count}]",
            "X-Eyesteel-Intent": intent_summary,
        },
    )


@router.post("/api/validate-universal-intent")
async def validate_universal_intent(body: UniversalStructuralIntent) -> JSONResponse:
    try:
        pure = await asyncio.to_thread(compile_universal_intent_to_pure_model, body)
        return JSONResponse(
            {
                "ok": True,
                "errors": [],
                "element_count": len(pure.elements),
                "slab_count": len(pure.slabs or []),
            }
        )
    except (GridFrameCompileError, PureVectorCompileError) as exc:
        return JSONResponse(
            {
                "ok": False,
                "errors": [str(exc)],
                "element_count": 0,
                "slab_count": 0,
            },
            status_code=422,
        )


@router.post("/api/intent-to-ifc")
async def intent_to_ifc(body: UniversalStructuralIntent) -> StreamingResponse:
    """Compile user-approved UniversalStructuralIntent → IFC bytes."""
    try:
        pure_model = await asyncio.to_thread(compile_universal_intent_to_pure_model, body)
        spec, constraints = await asyncio.to_thread(
            compile_pure_to_spec_with_constraints,
            "",
            pure_model,
        )
        ifc_bytes = await asyncio.to_thread(generate_ifc_from_spec, spec)
    except (GridFrameCompileError, PureVectorCompileError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IfcGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"IFC generation failed: {exc}") from exc

    if not ifc_bytes:
        raise HTTPException(status_code=500, detail="IFC generation returned empty output")

    segment_count = len(pure_model.elements)
    enforced = ",".join(sorted(constraints.keys())) or "geometry_only"
    group_types = ",".join(sorted({g.id for g in body.groups[:6]}))
    intent_summary = (
        f"region_crop;segments={segment_count};constraints={enforced};groups={group_types}"
    )
    return StreamingResponse(
        io.BytesIO(ifc_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="region-crop.ifc"',
            "X-Eyesteel-Spec": f"region crop · segments[{segment_count}]",
            "X-Eyesteel-Intent": intent_summary,
        },
    )

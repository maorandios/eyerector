from __future__ import annotations

import asyncio
import io
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from analyzer_service.ifc_generator import (
    IfcGenerationError,
    compile_pure_to_spec_with_constraints,
    generate_ifc_from_spec,
)
from analyzer_service.pdf_extract.extract import extract_structural_model_from_pdf
from analyzer_service.schemas import PureStructuralModelSpec

router = APIRouter()


class PdfIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_count: int
    likely_vector: bool
    text_char_count: int
    text_excerpt: str
    drawing_op_count: int = 0
    warnings: list[str]


class ValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    errors: list[str]
    warnings: list[str]
    element_count: int
    slab_count: int


class PdfToJsonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    message: str
    extraction_method: str = "vision_llm"
    ai_model: str | None = None
    ingest: PdfIngestResponse
    validation: ValidationResponse | None = None
    model: PureStructuralModelSpec | None = None
    warnings: list[str]


async def _read_upload(file: UploadFile) -> bytes:
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty PDF upload")
    return data


@router.post("/api/pdf-to-structural-json", response_model=PdfToJsonResponse)
async def pdf_to_structural_json(
    file: UploadFile = File(...),
    scale_note: str | None = Form(default=None),
    hints: str | None = Form(default=None),
) -> PdfToJsonResponse:
    """
  Upload a 2D structural steel plan PDF.
  Returns PureStructuralModelSpec JSON (mm segments + slabs) and a validation report.
  """
    data = await _read_upload(file)
    result = await asyncio.to_thread(
        extract_structural_model_from_pdf,
        data,
        scale_note=scale_note,
        extra_hints=hints,
    )
    ingest = PdfIngestResponse(
        page_count=result.ingest.page_count,
        likely_vector=result.ingest.likely_vector,
        text_char_count=result.ingest.text_char_count,
        text_excerpt=result.ingest.text_excerpt,
        drawing_op_count=result.ingest.drawing_op_count,
        warnings=result.ingest.warnings,
    )
    validation = None
    if result.validation:
        validation = ValidationResponse(
            ok=result.validation.ok,
            errors=result.validation.errors,
            warnings=result.validation.warnings,
            element_count=result.validation.element_count,
            slab_count=result.validation.slab_count,
        )
    return PdfToJsonResponse(
        status=result.status,
        message=result.message,
        extraction_method=result.extraction_method,
        ai_model=result.ai_model,
        ingest=ingest,
        validation=validation,
        model=result.model,
        warnings=result.warnings,
    )


@router.post("/api/pdf-to-ifc")
async def pdf_to_ifc(
    file: UploadFile = File(...),
    scale_note: str | None = Form(default=None),
    hints: str | None = Form(default=None),
) -> StreamingResponse:
    """PDF → validated PureStructuralModelSpec → IFC (same geometry path as chat-to-IFC)."""
    data = await _read_upload(file)
    result = await asyncio.to_thread(
        extract_structural_model_from_pdf,
        data,
        scale_note=scale_note,
        extra_hints=hints,
    )
    if result.model is None or result.status == "failed":
        raise HTTPException(
            status_code=422,
            detail={
                "message": result.message,
                "status": result.status,
                "warnings": result.warnings,
                "extraction_method": result.extraction_method,
                "ai_model": result.ai_model,
            },
        )
    if (
        result.extraction_method == "vision_llm"
        and result.status == "needs_review"
        and result.ingest.drawing_op_count > 500
        and len(result.model.elements) < 50
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    f"{result.message} "
                    "IFC export blocked: vision extraction is too incomplete for this CAD PDF."
                ),
                "status": result.status,
                "warnings": result.warnings,
                "extraction_method": result.extraction_method,
                "member_count": len(result.model.elements),
            },
        )
    if result.validation and not result.validation.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Validation failed",
                "errors": result.validation.errors,
            },
        )

    try:
        spec, _ = await asyncio.to_thread(
            compile_pure_to_spec_with_constraints,
            "",
            result.model,
        )
        ifc_bytes = await asyncio.to_thread(generate_ifc_from_spec, spec)
    except IfcGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    segment_count = len(result.model.elements)
    return StreamingResponse(
        io.BytesIO(ifc_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="from-plan.ifc"',
            "X-Eyesteel-Spec": f"pdf_extract · segments[{segment_count}]",
            "X-Eyesteel-Intent": f"pure_vector;source=pdf_{result.extraction_method};status={result.status}",
        },
    )


@router.post("/api/validate-structural-json")
async def validate_structural_json(body: PureStructuralModelSpec) -> JSONResponse:
    """Validate a client-supplied PureStructuralModelSpec before IFC export."""
    from analyzer_service.pdf_validate.validate import validate_pure_model

    report = validate_pure_model(body)
    return JSONResponse(
        {
            "ok": report.ok,
            "errors": report.errors,
            "warnings": report.warnings,
            "element_count": report.element_count,
            "slab_count": report.slab_count,
        }
    )

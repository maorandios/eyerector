from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from analyzer import extract_model_data
from analyzer_service.chat_to_ifc_router import router as chat_to_ifc_router
from analyzer_service.pdf_to_json_router import router as pdf_to_json_router
from analyzer_service.region_crop_router import router as region_crop_router
from analyzer_service.grid_model_router import router as grid_model_router
from analyzer_service.pdf_project_storage import projects_root


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="EyeSteel IFC Analyzer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    """Browser-friendly status; IFC generation is POST /api/chat-to-ifc."""
    return {
        "status": "ok",
        "pipeline": "pure_vector",
        "health": "/health",
        "chat_to_ifc": "POST /api/chat-to-ifc",
        "pdf_to_json": "POST /api/pdf-to-structural-json",
        "pdf_to_ifc": "POST /api/pdf-to-ifc",
        "upload_pdf": "POST /upload-pdf",
        "analyze_region": "POST /analyze-region",
        "intent_to_ifc": "POST /api/intent-to-ifc",
    }


@app.get("/health")
def health() -> dict[str, str]:
    import os

    from analyzer_service.pdf_extract.extract import _cad_lines_enabled, _pdf_extract_mode
    from analyzer_service.pdf_extract.vision import _vision_model_name
    from analyzer_service.region_vision import _region_vision_provider, region_vision_model_label

    mode = _pdf_extract_mode()
    cad_default = mode in ("cad", "vector", "lines") or _cad_lines_enabled() or mode == "auto"

    return {
        "status": "ok",
        "health_version": "2",
        "pipeline": "pure_vector",
        "chat_to_ifc": "extract_pure_structural_model",
        "pdf_pipeline": "CAD vectors (dense PDF) or vision → PureStructuralModelSpec → IFC",
        "pdf_extract_mode": mode,
        "pdf_dense_cad_primary": "vector_pdf" if cad_default else "vision_llm",
        "pdf_cad_lines": "enabled" if _cad_lines_enabled() else "auto_for_dense_cad",
        "openai_vision_model": _vision_model_name(),
        "openai_text_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        "region_vision_provider": _region_vision_provider(),
        "region_vision_model": region_vision_model_label(),
        "region_crop": "POST /upload-pdf, POST /api/vector-grid-extract, POST /api/align-pins, POST /api/region-column-clicks-finish",
    }


@app.post("/analyze-ifc")
async def analyze_ifc(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or "model.ifc"
    if not filename.lower().endswith(".ifc"):
        raise HTTPException(status_code=400, detail="Only IFC files are supported")

    with tempfile.TemporaryDirectory(prefix="eyesteel-ifc-") as temp_dir:
        ifc_path = Path(temp_dir) / "upload.ifc"
        with ifc_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        try:
            return await asyncio.to_thread(extract_model_data, str(ifc_path), False)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"IFC analyzer failed: {exc}") from exc
        finally:
            await file.close()


app.include_router(chat_to_ifc_router)
app.include_router(pdf_to_json_router)
app.include_router(region_crop_router)
app.include_router(grid_model_router)

_projects_root = projects_root()
_projects_root.mkdir(parents=True, exist_ok=True)
from fastapi.staticfiles import StaticFiles  # noqa: E402

app.mount(
    "/assets/pdf-projects",
    StaticFiles(directory=str(_projects_root)),
    name="pdf_projects",
)

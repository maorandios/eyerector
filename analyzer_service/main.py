from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from analyzer import extract_model_data


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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

"""On-disk storage for uploaded PDF page thumbnails."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import fitz

from analyzer_service.pdf_extract.vision import render_pdf_page_pngs
from analyzer_service.region_analysis_schemas import PageAsset, UploadPdfResponse

ASSETS_PREFIX = "/assets/pdf-projects"


def projects_root() -> Path:
    raw = os.getenv("PDF_PROJECTS_ROOT", "").strip()
    if raw:
        return Path(raw).resolve()
    root = Path(__file__).resolve().parents[1] / "data" / "pdf_projects"
    return root.resolve()


def _project_dpi() -> int:
    try:
        return int(os.getenv("PDF_PROJECT_DPI", "200").strip())
    except ValueError:
        return 200


def _max_pages() -> int:
    try:
        return int(os.getenv("PDF_PROJECT_MAX_PAGES", "24").strip())
    except ValueError:
        return 24


def _page_dimensions(png_bytes: bytes) -> tuple[int, int]:
    doc = fitz.open(stream=png_bytes, filetype="png")
    try:
        if doc.page_count < 1:
            return 1, 1
        rect = doc[0].rect
        return max(1, int(rect.width)), max(1, int(rect.height))
    finally:
        doc.close()


def project_dir(project_id: str) -> Path:
    safe = project_id.replace("/", "").replace("\\", "").strip()
    if not safe or safe != project_id:
        raise ValueError("invalid project_id")
    return projects_root() / safe


def load_manifest(project_id: str) -> dict:
    path = project_dir(project_id) / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"project not found: {project_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def create_project_from_pdf(data: bytes, filename: str = "upload.pdf") -> UploadPdfResponse:
    if not data:
        raise ValueError("empty PDF")
    project_id = uuid.uuid4().hex
    root = project_dir(project_id)
    pages_dir = root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (root / "crops").mkdir(exist_ok=True)

    (root / "source.pdf").write_bytes(data)

    rendered = render_pdf_page_pngs(
        data,
        max_pages=_max_pages(),
        dpi=_project_dpi(),
    )
    if not rendered:
        raise ValueError("PDF has no renderable pages")

    page_assets: list[PageAsset] = []
    for page_num, png_bytes in rendered:
        width_px, height_px = _page_dimensions(png_bytes)
        out_path = pages_dir / f"{page_num}.png"
        out_path.write_bytes(png_bytes)
        rel_url = f"{ASSETS_PREFIX}/{project_id}/pages/{page_num}.png"
        page_assets.append(
            PageAsset(
                page_index=page_num,
                width_px=width_px,
                height_px=height_px,
                url=rel_url,
            )
        )

    manifest = {
        "project_id": project_id,
        "filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(page_assets),
        "pages": [p.model_dump() for p in page_assets],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    base_url = f"{ASSETS_PREFIX}/{project_id}"
    return UploadPdfResponse(
        project_id=project_id,
        filename=filename,
        page_count=len(page_assets),
        base_url=base_url,
        pages=page_assets,
    )


def read_page_png(project_id: str, page_index: int) -> bytes:
    path = project_dir(project_id) / "pages" / f"{page_index}.png"
    if not path.is_file():
        raise FileNotFoundError(f"page {page_index} not found for project {project_id}")
    return path.read_bytes()


def save_crop_png(project_id: str, crop_id: str, png_bytes: bytes) -> str:
    crops_dir = project_dir(project_id) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    safe_id = crop_id.replace("/", "").replace("\\", "").strip() or uuid.uuid4().hex[:12]
    path = crops_dir / f"{safe_id}.png"
    path.write_bytes(png_bytes)
    return f"{ASSETS_PREFIX}/{project_id}/crops/{safe_id}.png"

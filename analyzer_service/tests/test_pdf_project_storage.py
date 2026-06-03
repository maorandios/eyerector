from __future__ import annotations

import json
import os
from pathlib import Path

import fitz
import pytest

from analyzer_service import pdf_project_storage as storage


def _minimal_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page(width=800, height=600)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def temp_projects_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "pdf_projects"
    monkeypatch.setenv("PDF_PROJECTS_ROOT", str(root))
    monkeypatch.setattr(storage, "projects_root", lambda: root.resolve())
    return root


def test_create_project_from_pdf_writes_manifest_and_pages(temp_projects_root: Path) -> None:
    result = storage.create_project_from_pdf(_minimal_pdf(), "test-plan.pdf")
    assert result.page_count == 1
    assert len(result.pages) == 1
    assert result.pages[0].page_index == 1
    assert result.pages[0].width_px > 0
    assert result.pages[0].height_px > 0
    assert f"/assets/pdf-projects/{result.project_id}/pages/1.png" in result.pages[0].url

    project_path = temp_projects_root / result.project_id
    assert (project_path / "source.pdf").is_file()
    assert (project_path / "pages" / "1.png").is_file()
    manifest = json.loads((project_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["project_id"] == result.project_id
    assert manifest["filename"] == "test-plan.pdf"


def test_read_page_png_roundtrip(temp_projects_root: Path) -> None:
    result = storage.create_project_from_pdf(_minimal_pdf())
    png = storage.read_page_png(result.project_id, 1)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

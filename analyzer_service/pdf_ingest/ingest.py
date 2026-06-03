"""PDF ingestion: page metadata, vector vs raster hint, text extraction."""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz  # PyMuPDF

from analyzer_service.pdf_extract.vector_geometry import _count_page_line_items


@dataclass
class PdfIngestReport:
    page_count: int
    likely_vector: bool
    text_char_count: int
    text_excerpt: str
    drawing_op_count: int = 0
    warnings: list[str] = field(default_factory=list)


def ingest_pdf_bytes(data: bytes, *, excerpt_limit: int = 48000) -> PdfIngestReport:
    warnings: list[str] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not open PDF: {exc}") from exc

    try:
        page_count = doc.page_count
        if page_count == 0:
            raise ValueError("PDF has no pages")

        text_parts: list[str] = []
        drawing_ops = 0
        for page_index, page in enumerate(doc):
            blocks = page.get_text("blocks")
            block_lines = [
                block[4].strip()
                for block in blocks
                if isinstance(block, (list, tuple)) and len(block) > 4 and str(block[4]).strip()
            ]
            if block_lines:
                text_parts.append(f"--- page {page_index + 1} ---\n" + "\n".join(block_lines))
            else:
                plain = page.get_text("text").strip()
                if plain:
                    text_parts.append(f"--- page {page_index + 1} ---\n{plain}")
            try:
                line_items = _count_page_line_items(page)
                path_count = sum(1 for _ in page.get_drawings())
                drawing_ops += max(line_items, path_count)
            except Exception:
                pass

        full_text = "\n\n".join(part.strip() for part in text_parts if part.strip())
        text_chars = len(full_text)
        likely_vector = drawing_ops > 20
        if text_chars < 80 and drawing_ops > 20:
            warnings.append(
                "Plan is CAD/vector-heavy — extracting real PDF linework first (not AI placeholder frames)."
            )
        elif drawing_ops > 500:
            warnings.append(
                "Large CAD PDF — using PDF vector lines as primary geometry; AI vision only if lines fail."
            )
        if not likely_vector and text_chars < 500:
            warnings.append("PDF may be a scan; vision quality depends on resolution and scale bar.")

        excerpt = full_text[:excerpt_limit]
        if len(full_text) > excerpt_limit:
            warnings.append(f"Text truncated to {excerpt_limit} characters for extraction.")

        return PdfIngestReport(
            page_count=page_count,
            likely_vector=likely_vector,
            text_char_count=text_chars,
            text_excerpt=excerpt,
            drawing_op_count=drawing_ops,
            warnings=warnings,
        )
    finally:
        doc.close()

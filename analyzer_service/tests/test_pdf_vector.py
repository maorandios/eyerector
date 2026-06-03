"""Vector PDF line extraction."""

import fitz

from analyzer_service.pdf_extract.extract import _primary_extraction_method
from analyzer_service.pdf_ingest.ingest import PdfIngestReport
from analyzer_service.pdf_extract.vector_geometry import extract_pure_model_from_pdf_vectors


def _minimal_line_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=2000, height=2000)
    shape = page.new_shape()
    shape.draw_line((100, 100), (1900, 100))
    shape.draw_line((100, 100), (100, 1900))
    shape.finish(color=(0, 0, 0), width=1.2)
    shape.commit()
    data = doc.tobytes()
    doc.close()
    return data


def test_dense_cad_defaults_to_cad_vectors() -> None:
    ingest = PdfIngestReport(
        page_count=6,
        likely_vector=True,
        text_char_count=50,
        text_excerpt="",
        drawing_op_count=239_131,
    )
    assert _primary_extraction_method(ingest) == "vector_pdf"


def test_extract_lines_from_vector_pdf() -> None:
    pdf = _minimal_line_pdf()
    model, warnings = extract_pure_model_from_pdf_vectors(pdf, scale_note="units mm")
    assert len(model.elements) >= 1
    assert any("CAD vector" in w for w in warnings)
    assert any("Structural lines kept" in w for w in warnings)

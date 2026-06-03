"""PDF extraction routing and completeness heuristics."""

from analyzer_service.pdf_extract.extract import _primary_extraction_method
from analyzer_service.pdf_ingest.ingest import PdfIngestReport
from analyzer_service.pdf_validate.completeness import check_extraction_completeness
from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec


def test_primary_is_vision_for_plan_pdf() -> None:
    ingest = PdfIngestReport(
        page_count=3,
        likely_vector=True,
        text_char_count=50,
        text_excerpt="",
        drawing_op_count=200,
    )
    assert _primary_extraction_method(ingest) == "vision_llm"


def test_primary_is_cad_vectors_for_dense_cad() -> None:
    ingest = PdfIngestReport(
        page_count=6,
        likely_vector=True,
        text_char_count=800,
        text_excerpt="grid A B",
        drawing_op_count=239_131,
    )
    assert _primary_extraction_method(ingest) == "vector_pdf"


def test_primary_is_text_for_spec_heavy_pdf() -> None:
    ingest = PdfIngestReport(
        page_count=1,
        likely_vector=False,
        text_char_count=15_000,
        text_excerpt="x" * 15_000,
        drawing_op_count=10,
    )
    assert _primary_extraction_method(ingest) == "text_llm"


def test_completeness_rejects_sparse_model_on_vector_pdf() -> None:
    ingest = PdfIngestReport(
        page_count=2,
        likely_vector=True,
        text_char_count=100,
        text_excerpt="",
        drawing_op_count=500,
    )
    model = PureStructuralModelSpec(
        elements=[
            PureSteelElementSpec(
                id="e1",
                profile_name="HEB300",
                start_x=0,
                start_y=0,
                start_z=0,
                end_x=30000,
                end_y=0,
                end_z=0,
            ),
        ],
        slabs=[],
    )
    report = check_extraction_completeness(model, ingest, extraction_method="text_llm")
    assert report.ok is False
    assert "OpenAI text" in report.message


def test_completeness_allows_partial_vision_on_dense_cad() -> None:
    ingest = PdfIngestReport(
        page_count=6,
        likely_vector=True,
        text_char_count=100,
        text_excerpt="",
        drawing_op_count=239_131,
    )
    elements = [
        PureSteelElementSpec(
            id=f"e{i}",
            profile_name="HEB300",
            start_x=float(i * 1000),
            start_y=0.0,
            start_z=0.0,
            end_x=float(i * 1000 + 5000),
            end_y=0.0,
            end_z=0.0,
        )
        for i in range(10)
    ]
    model = PureStructuralModelSpec(elements=elements, slabs=[])
    report = check_extraction_completeness(model, ingest, extraction_method="vision_llm")
    assert report.ok is True
    assert "Vision extracted" in report.message

"""Heuristic checks that PDF extraction produced enough geometry."""

from __future__ import annotations

from dataclasses import dataclass

from analyzer_service.pdf_ingest.ingest import PdfIngestReport
from analyzer_service.schemas import PureStructuralModelSpec


@dataclass
class CompletenessReport:
    ok: bool
    message: str = ""


def check_extraction_completeness(
    model: PureStructuralModelSpec,
    ingest: PdfIngestReport,
    *,
    extraction_method: str,
) -> CompletenessReport:
    n = len(model.elements)
    slabs = len(model.slabs or [])

    if extraction_method == "vector_pdf":
        if n < 20:
            return CompletenessReport(
                ok=False,
                message=(
                    f"Vector extraction found only {n} line segments in a CAD PDF "
                    f"(~{ingest.drawing_op_count} drawing items). "
                    "Check scale (e.g. units mm) or lower PDF_VECTOR_MIN_LENGTH_MM."
                ),
            )
        return CompletenessReport(ok=True)

    if extraction_method == "vision_llm" and ingest.drawing_op_count > 80 and n < 5:
        return CompletenessReport(
            ok=False,
            message=(
                f"OpenAI vision extracted only {n} steel members (PDF has {ingest.page_count} sheets, "
                f"~{ingest.drawing_op_count} CAD lines). Vision reads a picture, not CAD vectors — "
                "dense plans often stay incomplete. Use Hints: page N for the main floor plan, "
                "Scale: units mm, or the text AI Designer for full 3D."
            ),
        )

    if extraction_method == "vision_llm" and ingest.drawing_op_count > 80 and n < 12:
        return CompletenessReport(
            ok=True,
            message=(
                f"Vision extracted {n} members from a dense CAD sheet — partial result is expected; "
                "review JSON or use AI Designer for a full model."
            ),
        )

    if extraction_method == "text_llm" and ingest.drawing_op_count > 80 and n < 12:
        return CompletenessReport(
            ok=False,
            message=(
                f"OpenAI text extracted only {n} steel members — text cannot read CAD line geometry. "
                "This PDF needs vision_llm (set OPENAI_VISION_MODEL to gpt-4o or gpt-4o-2024-11-20). "
                "Check API logs for vision_llm errors."
            ),
        )

    if ingest.drawing_op_count > 80 and n < 12:
        return CompletenessReport(
            ok=False,
            message=(
                f"Only {n} steel segments were extracted from a dense CAD PDF "
                f"(method: {extraction_method}). "
                "Enable OpenAI vision (default) — not a weaker text model. "
                "Set OPENAI_VISION_MODEL to gpt-4o-2024-11-20 or gpt-4o in .env.local."
            ),
        )

    if n <= 4 and slabs <= 1 and ingest.page_count >= 1:
        span = _bounding_span_mm(model)
        if span and span > 20_000 and n <= 4:
            return CompletenessReport(
                ok=False,
                message=(
                    f"Output looks like a single simplified box (~{span:.0f} mm span) with only {n} members. "
                    "This usually means the drawing lines were not parsed. "
                    f"Extraction used: {extraction_method}."
                ),
            )

    if ingest.text_char_count < 100 and n < 10 and extraction_method == "text_llm":
        return CompletenessReport(
            ok=False,
            message="Text-only extraction on a drawing PDF is unreliable; retry with vision enabled.",
        )

    return CompletenessReport(ok=True)


def _bounding_span_mm(model: PureStructuralModelSpec) -> float | None:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for el in model.elements:
        xs.extend((el.start_x, el.end_x))
        ys.extend((el.start_y, el.end_y))
        zs.extend((el.start_z, el.end_z))
    for slab in model.slabs or []:
        xs.extend((slab.min_x, slab.max_x))
        ys.extend((slab.min_y, slab.max_y))
        zs.extend((slab.min_z, slab.max_z))
    if not xs:
        return None
    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

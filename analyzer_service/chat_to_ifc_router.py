from __future__ import annotations

import asyncio
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from analyzer_service.ifc_generator import (
    IfcGenerationError,
    compile_pure_to_spec_with_constraints,
    generate_ifc_from_spec,
)
from analyzer_service.llm_extractor import LlmExtractionError, extract_pure_structural_model
from analyzer_service.structured_intent_parser import parse_structured_prompt_to_universal_intent
from analyzer_service.schemas import ChatToIfcRequest

router = APIRouter()


@router.post("/api/chat-to-ifc")
async def chat_to_ifc(body: ChatToIfcRequest) -> StreamingResponse:
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    history = body.resolved_history()

    try:
        pure_model = await asyncio.to_thread(extract_pure_structural_model, prompt, history)
        spec, constraints = await asyncio.to_thread(
            compile_pure_to_spec_with_constraints,
            prompt,
            pure_model,
        )
        ifc_bytes = await asyncio.to_thread(generate_ifc_from_spec, spec)
    except LlmExtractionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IfcGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"IFC generation failed: {exc}") from exc

    if not ifc_bytes:
        raise HTTPException(status_code=500, detail="IFC generation returned empty output")

    segment_count = len(pure_model.elements)
    slab_count = len(pure_model.slabs or [])
    enforced = ",".join(sorted(constraints.keys())) or "geometry_only"
    structured = parse_structured_prompt_to_universal_intent(prompt)
    source = "generic_sections+geometry" if structured else "llm_intent+geometry"
    tier_hint = ""
    if structured:
        group_ids = {group.id for group in structured.groups}
        if "level2_cantilevers" in group_ids:
            tier_hint = ";tiers=stepdown"
        elif "web_members" in group_ids or "web_members_warren" in group_ids:
            tier_hint = ";tiers=roof_truss"
    intent_summary = (
        f"pure_vector;source={source};segments={segment_count};slabs={slab_count}"
        f";constraints={enforced}{tier_hint}"
    )
    return StreamingResponse(
        io.BytesIO(ifc_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="ai-generated.ifc"',
            "X-Eyesteel-Spec": f"pure vector compiler · segments[{segment_count}]",
            "X-Eyesteel-Intent": intent_summary,
        },
    )

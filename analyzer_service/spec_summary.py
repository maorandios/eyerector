"""Human-readable summary for API headers / chat UI."""

from __future__ import annotations

from analyzer_service.schemas import (
    DynamicGraphLayoutRequest,
    ParametricLayoutRequest,
    StructuralElement,
    StructuralModelSpec,
)


def format_spec_summary(spec: StructuralModelSpec) -> str:
    cols = [e for e in spec.elements if e.type == "column"]
    beams = [e for e in spec.elements if e.type == "beam"]

    def profile_line(e: StructuralElement) -> str:
        key = e.profile_key or e.profile_type
        return f"{key} ({int(e.length_mm)} mm)"

    parts: list[str] = []
    if cols:
        keys = {profile_line(c) for c in cols}
        parts.append(f"{len(cols)}× column: {', '.join(sorted(keys))}")
    if beams:
        keys = {profile_line(b) for b in beams}
        parts.append(f"{len(beams)}× beam: {', '.join(sorted(keys))}")
    return " · ".join(parts) if parts else "empty model"


def format_layout_summary(intent: ParametricLayoutRequest, spec: StructuralModelSpec) -> str:
    layout_label = intent.layout_type.replace("_", " ")
    detail = format_spec_summary(spec)
    return f"{layout_label} · {detail}"


def format_graph_summary(graph: DynamicGraphLayoutRequest) -> str:
    columns = [e for e in graph.elements if e.type == "column"]
    beams = [e for e in graph.elements if e.type == "beam"]
    col_profiles = sorted({c.profile_name for c in columns})
    beam_profiles = sorted({b.profile_name for b in beams})
    return (
        f"graph · {len(columns)}× column ({', '.join(col_profiles) or 'n/a'})"
        f" · {len(beams)}× beam ({', '.join(beam_profiles) or 'n/a'})"
    )

"""
Generic prompt → UniversalStructuralIntent (grid dimensions + level elevations + member groups).

No building-type routing (no warehouse / mezzanine / N-story switches).
Rules apply from numeric sections and level lists present in the text.
"""

from __future__ import annotations

import re

from analyzer_service.schemas import (
    GridFrameSpec,
    LevelSpec,
    SlabGroupSpec,
    StructuralGroupSpec,
    UniversalStructuralIntent,
)


def _mm(prompt: str, pattern: str) -> float | None:
    m = re.search(pattern, prompt, re.IGNORECASE)
    if not m or m.lastindex is None or m.group(1) is None:
        return None
    return float(m.group(1))


def _count(prompt: str, pattern: str) -> int | None:
    m = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
    return int(m.group(1)) if m else None


def _roof_elevation_mm(prompt: str, kind: str) -> float | None:
    if kind == "eave":
        patterns = [
            r"Roof Eave[^\n\r]*Z\s*=\s*(\d+(?:\.\d+)?)\s*mm",
            r"Eave Height[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
            r"Top of Column[^\n\r]*Z\s*=\s*(\d+(?:\.\d+)?)\s*mm",
        ]
    else:
        patterns = [
            r"Roof Ridge[^\n\r]*Z\s*=\s*(\d+(?:\.\d+)?)\s*mm",
            r"Ridge Height[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
            r"Apex[^\n\r]*Z\s*=\s*(\d+(?:\.\d+)?)\s*mm",
        ]
    for pattern in patterns:
        value = _mm(prompt, pattern)
        if value is not None:
            return value
    return None


def _profile_after(prompt: str, section_keyword: str, default_key: str) -> str:
    section = re.search(rf"(?:{section_keyword})[\s\S]{{0,320}}", prompt, re.IGNORECASE)
    key_pattern = (
        r"((?:IPE|HEA|HEB|HEM|UPN|UPE)\s*\d{2,4}"
        r"|RHS\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?"
        r"|CHS\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?"
        r"|[CZ]\s*\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?)"
    )
    if section:
        m = re.search(rf"Profile\s*:\s*{key_pattern}", section.group(0), re.IGNORECASE)
        if not m:
            m = re.search(key_pattern, section.group(0), re.IGNORECASE)
        if m:
            raw = m.group(1).strip().upper().replace(" ", "")
            if raw.startswith("CHS"):
                return raw
            if raw.startswith("Z"):
                return "100x100x6"
            if raw.startswith("C") and not raw.startswith("CHS"):
                return "100x50x4"
            return raw
    return default_key


# Do not use greedy [^\n\r]* before Z= on single-line prompts — it can skip to a later Level/Ridge Z.
_LEVEL_Z_PATTERN = re.compile(
    r"Level\s*(\d+)(?:(?!Level\s*\d)[^\n\r])*?Z\s*=\s*(\d+(?:\.\d+)?)\s*mm",
    re.IGNORECASE,
)
_FLOOR_Z_PATTERN = re.compile(
    r"Floor\s*(\d+)(?:(?!Floor\s*\d)[^\n\r])*?Z\s*=\s*(\d+(?:\.\d+)?)\s*mm",
    re.IGNORECASE,
)


def _normalize_prompt_for_parsing(prompt: str) -> str:
    """Break dense single-line engineering prompts so section-local regexes stay accurate."""
    if prompt.count("\n") >= 8:
        return prompt
    text = prompt
    text = re.sub(r"\s+(?=\d+\.\s+[A-Z])", "\n", text)
    text = re.sub(r"\s+-\s+", "\n- ", text)
    return text


def _collect_levels(prompt: str) -> list[LevelSpec]:
    prompt = _normalize_prompt_for_parsing(prompt)
    levels: list[LevelSpec] = [LevelSpec(name="Ground", elevation_mm=0.0)]
    seen: set[str] = {"Ground"}

    for m in _LEVEL_Z_PATTERN.finditer(prompt):
        name = f"Level{int(m.group(1))}"
        if name not in seen:
            levels.append(LevelSpec(name=name, elevation_mm=float(m.group(2))))
            seen.add(name)

    for m in _FLOOR_Z_PATTERN.finditer(prompt):
        num = int(m.group(1))
        if num <= 1:
            continue
        name = f"Floor{num}"
        if name in seen:
            continue
        levels.append(LevelSpec(name=name, elevation_mm=float(m.group(2))))
        seen.add(name)

    col_top = _mm(prompt, r"from Z=0 to Z=(\d+(?:\.\d+)?)")
    if col_top is not None and "ColumnTop" not in seen:
        levels.append(LevelSpec(name="ColumnTop", elevation_mm=float(col_top)))
        seen.add("ColumnTop")

    deck_top = _mm(prompt, r"Finished Deck Elevation[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm")
    if deck_top is None:
        deck_top = _mm(prompt, r"top face at Z\s*=\s*(\d+(?:\.\d+)?)")
    if deck_top is not None and "DeckTop" not in seen:
        levels.append(LevelSpec(name="DeckTop", elevation_mm=float(deck_top)))
        seen.add("DeckTop")

    eave = _mm(prompt, r"(?:Main Roof )?Eave[^\n\r]{0,160}?Z\s*=\s*(\d+(?:\.\d+)?)\s*mm")
    if eave is None:
        eave = _mm(prompt, r"Top of Main Columns[^\n\r]{0,160}?Z\s*=\s*(\d+(?:\.\d+)?)\s*mm")
    if eave is None:
        eave = _roof_elevation_mm(prompt, "eave")
    if eave is not None and "Eave" not in seen:
        levels.append(LevelSpec(name="Eave", elevation_mm=float(eave)))
        seen.add("Eave")

    ridge = _roof_elevation_mm(prompt, "ridge")
    if ridge is not None and "Ridge" not in seen:
        levels.append(LevelSpec(name="Ridge", elevation_mm=float(ridge)))
        seen.add("Ridge")

    mezzanine_z = _mm(prompt, r"Mezzanine Floor[^\n\r]*Z\s*=\s*(\d+(?:\.\d+)?)\s*mm")
    if mezzanine_z is not None and "Deck" not in seen:
        levels.append(LevelSpec(name="Deck", elevation_mm=float(mezzanine_z)))
        seen.add("Deck")

    upper_anchor_z = _mm(prompt, r"Upper Anchor[^\n\r]*Z\s*=\s*(\d+(?:\.\d+)?)\s*mm")
    if upper_anchor_z is not None and "UpperAnchor" not in seen:
        levels.append(LevelSpec(name="UpperAnchor", elevation_mm=float(upper_anchor_z)))
        seen.add("UpperAnchor")

    guardrail_z = _mm(
        prompt,
        r"(?:GUARDRAIL|guardrail|מעקה)[\s\S]{0,200}?Z\s*=\s*(\d+(?:\.\d+)?)\s*(?:mm)?",
    )
    if guardrail_z is None:
        guardrail_z = _mm(prompt, r"guardrail[^\n]{0,120}?\bat\s+Z\s*=\s*(\d+(?:\.\d+)?)")
    if guardrail_z is not None and "Guardrail" not in seen:
        levels.append(LevelSpec(name="Guardrail", elevation_mm=float(guardrail_z)))
        seen.add("Guardrail")

    brace_z = _mm(prompt, r"column body \(at Z=(\d+(?:\.\d+)?)\)")
    if brace_z is not None and "BraceStart" not in seen:
        levels.append(LevelSpec(name="BraceStart", elevation_mm=float(brace_z)))
        seen.add("BraceStart")

    return sorted(levels, key=lambda level: level.elevation_mm)


def _column_top_level(levels: list[LevelSpec]) -> str:
    if any(level.name == "Eave" for level in levels):
        return "Eave"
    if any(level.name == "ColumnTop" for level in levels):
        return "ColumnTop"
    return max(levels, key=lambda level: level.elevation_mm).name


def _floor_framing_groups(
    *,
    prefix: str,
    level: str,
    primary_profile: str,
    joist_profile: str,
    joist_spacing_mm: float,
) -> list[StructuralGroupSpec]:
    return [
        StructuralGroupSpec(
            id=f"{prefix}_primary_x",
            profile_name=primary_profile,
            orientation="horizontal_x",
            assigned_to_grid="along_x_between_columns",
            start_level=level,
            end_level=level,
            category="beam",
        ),
        StructuralGroupSpec(
            id=f"{prefix}_primary_y",
            profile_name=primary_profile,
            orientation="horizontal_y",
            assigned_to_grid="along_y_at_frame_ends",
            start_level=level,
            end_level=level,
            member_count=2,
            category="beam",
        ),
        StructuralGroupSpec(
            id=f"{prefix}_joists",
            profile_name=joist_profile,
            orientation="horizontal_y",
            assigned_to_grid="distributed_along_x",
            start_level=level,
            end_level=level,
            spacing_mm=joist_spacing_mm,
            category="beam",
        ),
    ]


def _roof_groups(prompt: str, levels: list[LevelSpec]) -> list[StructuralGroupSpec]:
    if not any(level.name == "Eave" for level in levels) or not any(
        level.name == "Ridge" for level in levels
    ):
        return []

    purlin_count = (
        _count(prompt, r"(\d+)\s+lines\s+of\s+Z")
        or _count(prompt, r"Roof Purlins[^\n]{0,80}?(\d+)\s+lines")
        or _count(prompt, r"(\d+)\s+lines[^\n]{0,40}longitudinally")
    )
    girt_count = _count(prompt, r"(\d+)\s+lines\s+of\s+C") or 8
    web_per_frame = _count(prompt, r"Web Members[\s\S]{0,160}?(\d+)\s*Units per frame") or 8
    warren_web = bool(re.search(r"Warren\s+truss", prompt, re.IGNORECASE)) or bool(
        re.search(r"Warren\s+truss\s+pattern", prompt, re.IGNORECASE)
    )
    eave_z = next(level.elevation_mm for level in levels if level.name == "Eave")
    girt_elevations = [float(eave_z) * i / float(girt_count) for i in range(1, int(girt_count) + 1)]

    return [
        StructuralGroupSpec(
            id="top_chords",
            profile_name=_profile_after(prompt, r"Top Rafter Chords|Top Chords|חגורה עליונה", "IPE300"),
            orientation="inclined_dual_y",
            assigned_to_grid="all_frame_lines",
            start_level="Eave",
            end_level="Ridge",
            category="beam",
        ),
        StructuralGroupSpec(
            id="bottom_chords",
            profile_name=_profile_after(prompt, r"Bottom Chord Ties|Bottom Chord|חגורה תחתונה", "HEA220"),
            orientation="horizontal_y_per_frame",
            assigned_to_grid="along_y_per_frame_line",
            start_level="Eave",
            end_level="Eave",
            category="beam",
        ),
        StructuralGroupSpec(
            id="web_members_warren" if warren_web else "web_members",
            profile_name=_profile_after(prompt, r"Web Members|פנימיים", "RHS90x90x6"),
            orientation="truss_web_panels",
            assigned_to_grid="all_frame_lines",
            start_level="Eave",
            end_level="Ridge",
            member_count=int(web_per_frame),
            category="beam",
        ),
        StructuralGroupSpec(
            id="roof_purlins",
            profile_name=_profile_after(prompt, r"ROOF PURLINS|מרישי גג", "100x100x6"),
            orientation="roof_purlins_dual_slope",
            assigned_to_grid="all_frame_lines",
            start_level="Eave",
            end_level="Ridge",
            member_count=int(purlin_count or 10),
            category="beam",
        ),
        StructuralGroupSpec(
            id="wall_girts",
            profile_name=_profile_after(prompt, r"WALL GIRTS|מרישי קיר", "100x50x4"),
            orientation="wall_girts_fixed_z",
            assigned_to_grid="all_frame_lines",
            start_level="Eave",
            end_level="Eave",
            fixed_elevations_mm=girt_elevations,
            category="beam",
        ),
    ]


def _groups_from_quantity_sections(
    prompt: str,
    *,
    levels: list[LevelSpec],
    width_mm: float,
) -> list[StructuralGroupSpec]:
    """
    Build member groups from explicit '- N Units/Lines Total' sections in the prompt.
    Uses geometry rules only; section headers are treated as labels, not building types.
    """
    deck_level = next((level.name for level in levels if level.name in ("Deck", "DeckTop")), None)
    upper_level = next((level.name for level in levels if level.name == "UpperAnchor"), None)
    guardrail_level = next((level.name for level in levels if level.name == "Guardrail"), None)

    groups: list[StructuralGroupSpec] = []

    column_count = _count(prompt, r"COLUMNS[\s\S]{0,200}?(\d+)\s*Units\s*Total")
    if column_count is None:
        column_count = _count(prompt, r"COLUMNS[\s\S]{0,200}?-\s*(\d+)\s*Units")

    cantilever_count = _count(prompt, r"CANTILEVER[\s\S]{0,200}?(\d+)\s*Units\s*Total")
    if cantilever_count is None:
        cantilever_count = _count(prompt, r"PRIMARY BEAMS[\s\S]{0,200}?(\d+)\s*Units\s*Total")

    joist_count = _count(prompt, r"JOISTS[\s\S]{0,200}?(\d+)\s*Lines\s*Total")
    joist_spacing = (
        _mm(prompt, r"every\s*(\d+(?:\.\d+)?)\s*mm across")
        or _mm(prompt, r"every\s*(\d+(?:\.\d+)?)\s*mm along the X-axis")
        or _mm(prompt, r"every\s*(\d+(?:\.\d+)?)\s*mm")
    )

    tension_count = _count(prompt, r"TENSION[\s\S]{0,200}?(\d+)\s*Units\s*Total")
    if tension_count is None:
        tension_count = _count(prompt, r"RODS[\s\S]{0,200}?(\d+)\s*Units\s*Total")

    column_top = upper_level or next(
        (level.name for level in levels if level.name in ("Eave", "ColumnTop")),
        None,
    )
    if column_count is not None and column_top:
        groups.append(
            StructuralGroupSpec(
                id="columns_along_y_min",
                profile_name=_profile_after(prompt, r"REAR ANCHOR COLUMNS|ANCHOR COLUMNS", "HEB400"),
                orientation="vertical",
                assigned_to_grid="along_all_x_at_y_min",
                start_level="Ground",
                end_level=column_top,
                member_count=column_count,
                category="column",
            )
        )

    if cantilever_count is not None and deck_level:
        groups.append(
            StructuralGroupSpec(
                id="beams_along_y_per_x",
                profile_name=_profile_after(prompt, r"CANTILEVER PRIMARY BEAMS|CANTILEVER.*PRIMARY", "IPE450"),
                orientation="horizontal_y_per_frame",
                assigned_to_grid="along_y_per_frame_line",
                start_level=deck_level,
                end_level=deck_level,
                member_count=cantilever_count,
                category="beam",
            )
        )

    if joist_count is not None and deck_level:
        groups.append(
            StructuralGroupSpec(
                id="joists_along_x_spaced_y",
                profile_name=_profile_after(prompt, r"JOISTS|IPE160", "IPE160"),
                orientation="horizontal_x",
                assigned_to_grid="distributed_along_y",
                start_level=deck_level,
                end_level=deck_level,
                spacing_mm=float(joist_spacing or (width_mm / max(1, joist_count - 1))),
                member_count=joist_count,
                category="beam",
            )
        )

    if tension_count is not None and deck_level and upper_level:
        groups.append(
            StructuralGroupSpec(
                id="diagonals_per_x",
                profile_name=_profile_after(prompt, r"TENSION\s+SUSPENSION\s+RODS", "CHS60x5"),
                orientation="diagonal_plan",
                assigned_to_grid="per_x_station",
                start_level=upper_level,
                end_level=deck_level,
                member_count=tension_count,
                category="brace",
            )
        )

    if guardrail_level and re.search(r"GUARDRAIL|guardrail|מעקה", prompt, re.IGNORECASE):
        groups.extend(
            [
                StructuralGroupSpec(
                    id="edge_at_x_min",
                    profile_name=_profile_after(prompt, r"GUARDRAIL|RHS50", "RHS50x50x4"),
                    orientation="horizontal_y",
                    assigned_to_grid="along_y_at_x_min",
                    start_level=guardrail_level,
                    end_level=guardrail_level,
                    category="beam",
                ),
                StructuralGroupSpec(
                    id="edge_at_y_max",
                    profile_name=_profile_after(prompt, r"GUARDRAIL|RHS50", "RHS50x50x4"),
                    orientation="horizontal_x",
                    assigned_to_grid="along_x_at_y_max",
                    start_level=guardrail_level,
                    end_level=guardrail_level,
                    category="beam",
                ),
                StructuralGroupSpec(
                    id="edge_at_x_max",
                    profile_name=_profile_after(prompt, r"GUARDRAIL|RHS50", "RHS50x50x4"),
                    orientation="horizontal_y",
                    assigned_to_grid="along_y_at_x_max",
                    start_level=guardrail_level,
                    end_level=guardrail_level,
                    category="beam",
                ),
            ]
        )

    return groups


def _roof_brace_groups(prompt: str, levels: list[LevelSpec]) -> list[StructuralGroupSpec]:
    if not re.search(r"Roof Plane Bracing|roof plane bracing", prompt, re.IGNORECASE):
        return []
    if not any(level.name == "Eave" for level in levels) or not any(
        level.name == "Ridge" for level in levels
    ):
        return []
    profile = _profile_after(prompt, r"Roof Plane Bracing|CHS60x4", "CHS60x4")
    return [
        StructuralGroupSpec(
            id="roof_plane_bracing",
            profile_name=profile,
            orientation="diagonal_plan",
            assigned_to_grid="roof_truss_diagonals",
            start_level="Eave",
            end_level="Ridge",
            category="brace",
        )
    ]


def _wall_brace_groups(prompt: str, levels: list[LevelSpec]) -> list[StructuralGroupSpec]:
    if not re.search(r"Wall Bracing|הקשחה|cross-brace|X-BRACING", prompt, re.IGNORECASE):
        return []

    profile = _profile_after(prompt, r"Vertical Wall Bracing|Wall Bracing|CHS76", "CHS76x4")
    column_top = next(
        (level.name for level in levels if level.name in ("Eave", "ColumnTop")),
        _column_top_level(levels),
    )
    if re.search(
        r"(?:column bases|column tops|from Z\s*=\s*0).*?(?:to|Z\s*=\s*)\s*(\d+(?:\.\d+)?)",
        prompt,
        re.IGNORECASE,
    ) or (
        re.search(r"Vertical Wall Bracing", prompt, re.IGNORECASE)
        and "Ground" in {level.name for level in levels}
        and any(level.name in ("Eave", "ColumnTop") for level in levels)
        and not re.search(r"Wall Bracing[\s\S]{0,120}Level\s*\d", prompt, re.IGNORECASE)
    ):
        return [
            StructuralGroupSpec(
                id="wall_brace_full_height",
                profile_name=profile,
                orientation="diagonal_plan",
                assigned_to_grid="first_and_last_bay_braces",
                start_level="Ground",
                end_level=column_top,
                category="brace",
            )
        ]

    ordered = sorted(
        (level for level in levels if level.name not in ("Ridge", "BraceStart", "Guardrail")),
        key=lambda level: level.elevation_mm,
    )
    groups: list[StructuralGroupSpec] = []
    for index in range(len(ordered) - 1):
        start = ordered[index]
        end = ordered[index + 1]
        if end.elevation_mm - start.elevation_mm <= 1e-6:
            continue
        groups.append(
            StructuralGroupSpec(
                id=f"wall_brace_{start.name}_{end.name}",
                profile_name=profile,
                orientation="diagonal_plan",
                assigned_to_grid="first_and_last_bay_braces",
                start_level=start.name,
                end_level=end.name,
                category="brace",
            )
        )
    return groups


def _explicit_y_grid_lines(prompt: str) -> list[float]:
    values = [
        float(match.group(1))
        for match in re.finditer(r"Grid Line Y\s*=\s*(\d+(?:\.\d+)?)", prompt, re.IGNORECASE)
    ]
    if not values:
        for match in re.finditer(
            r"(?:along\s+)?grid\s+lines?\s+Y\s*=\s*(\d+(?:\.\d+)?)",
            prompt,
            re.IGNORECASE,
        ):
            values.append(float(match.group(1)))
    return sorted(set(values))


def _infer_triple_column_y_grid(
    *,
    width: float,
    col_count: int | None,
    frames_along_x: int,
) -> list[float]:
    """Default Y=0 / mid-span / far wall when prompt says 33 columns on 11 X lines but omits Grid Line Y=."""
    if col_count is None or frames_along_x < 2:
        return []
    if col_count != frames_along_x * 3:
        return []
    return [0.0, float(width) / 2.0, float(width)]


def _deck_slab_top_level(levels: list[LevelSpec]) -> str:
    for name in ("DeckTop", "Deck", "Level1"):
        if any(level.name == name for level in levels):
            return name
    skip = {"Ground", "Eave", "Ridge", "UpperAnchor", "Guardrail", "ColumnTop", "BraceStart"}
    elevated = [level for level in levels if level.name not in skip]
    if elevated:
        return max(elevated, key=lambda level: level.elevation_mm).name
    return "DeckTop"


def _append_generic_deck_slabs(
    prompt: str,
    levels: list[LevelSpec],
    *,
    slab_t: float,
    slabs: list[SlabGroupSpec],
) -> None:
    """Mezzanine / floating gallery decks (IfcSlab) when not already covered by level1_deck_slab."""
    if any(s.id in ("deck_slab", "level1_deck_slab", "mezzanine_deck_slab") for s in slabs):
        return
    if not re.search(
        r"MEZZANINE FLOOR DECK|\bFLOOR SLAB\b|(?:^|\n)\s*Floor Deck\b",
        prompt,
        re.IGNORECASE,
    ):
        return
    thickness = (
        _mm(prompt, r"Dimensions:[^\n]*Thickness\s*=\s*(\d+(?:\.\d+)?)\s*mm")
        or _mm(prompt, r"Thickness\s*=\s*(\d+(?:\.\d+)?)\s*mm")
        or float(slab_t)
    )
    slabs.append(
        SlabGroupSpec(
            id="deck_slab",
            top_level=_deck_slab_top_level(levels),
            thickness_mm=float(thickness),
            footprint="full_grid",
        )
    )


def _level_x_spans(prompt: str) -> dict[int, tuple[float, float]]:
    spans: dict[int, tuple[float, float]] = {}
    for match in re.finditer(
        r"Level\s*(\d+)(?:(?!Level\s*\d)[^\n]){0,320}?(?:Spanning|spanning)[^\n]{0,120}?X\s*=\s*0\s*to\s*X\s*=\s*(\d+(?:\.\d+)?)",
        prompt,
        re.IGNORECASE,
    ):
        spans[int(match.group(1))] = (0.0, float(match.group(2)))
    for match in re.finditer(
        r"Level\s*(\d+)(?:(?!Level\s*\d)[^\n]){0,320}?(?:from|From)\s+X\s*=\s*(\d+(?:\.\d+)?)\s*to\s*X\s*=\s*(\d+(?:\.\d+)?)",
        prompt,
        re.IGNORECASE,
    ):
        spans[int(match.group(1))] = (float(match.group(2)), float(match.group(3)))
    return spans


def _level2_deck_y_bounds(prompt: str) -> tuple[float, float]:
    match = re.search(
        r"projecting out from Y\s*=\s*(\d+(?:\.\d+)?)\s*to\s*Y\s*=\s*(\d+(?:\.\d+)?)",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return float(match.group(1)), float(match.group(2))
    return 0.0, 10000.0


def _cantilever_y_endpoints(prompt: str) -> tuple[float, float]:
    spine = re.search(
        r"(?:spine|Spine)[^\n]{0,80}?Y\s*=\s*(\d+(?:\.\d+)?)",
        prompt,
        re.IGNORECASE,
    )
    edge = re.search(
        r"(?:floating edge|outer floating tips)[^\n]{0,80}?Y\s*=\s*(\d+(?:\.\d+)?)",
        prompt,
        re.IGNORECASE,
    )
    if spine and edge:
        return float(spine.group(1)), float(edge.group(1))
    return 15000.0, 5000.0


def _groups_from_multi_level_sections(
    prompt: str,
    *,
    levels: list[LevelSpec],
    length: float,
    width: float,
    bay: float,
    y_grid: list[float],
) -> list[StructuralGroupSpec]:
    """Expand prompts with Level N zones, partial X spans, and explicit Y grid lines."""
    if not re.search(r"Level\s*1\b", prompt, re.IGNORECASE):
        return []
    if not any(level.name == "Level1" for level in levels):
        return []

    spans = _level_x_spans(prompt)
    y_spine, y_float = _cantilever_y_endpoints(prompt)
    frames_along_x = int(round(float(length) / float(bay))) + 1
    groups: list[StructuralGroupSpec] = []

    col_count = _count(prompt, r"(?:VERTICAL|DUAL-GRID) COLUMNS[\s\S]{0,240}?(\d+)\s*Units")
    column_top = next((level.name for level in levels if level.name == "Eave"), _column_top_level(levels))
    effective_y_grid = y_grid or _infer_triple_column_y_grid(
        width=float(width),
        col_count=col_count,
        frames_along_x=frames_along_x,
    )
    if col_count is not None and effective_y_grid and col_count == frames_along_x * len(effective_y_grid):
        groups.append(
            StructuralGroupSpec(
                id="grid_columns",
                profile_name=_profile_after(prompt, r"VERTICAL COLUMNS|DUAL-GRID", "HEB450"),
                orientation="vertical",
                assigned_to_grid="all_frame_lines",
                start_level="Ground",
                end_level=column_top,
                member_count=col_count,
                category="column",
            )
        )

    level1_span = spans.get(1, (0.0, float(length) / 2.0))
    primary_count = _count(prompt, r"Level 1[\s\S]{0,500}?Primary Beams[\s\S]{0,120}?(\d+)\s*Units")
    groups.append(
        StructuralGroupSpec(
            id="level1_primary_beams",
            profile_name=_profile_after(prompt, r"Level 1[\s\S]{0,500}?Primary Beams", "HEB300"),
            orientation="horizontal_x",
            assigned_to_grid="along_x_at_each_y_line",
            start_level="Level1",
            end_level="Level1",
            x_max_mm=level1_span[1],
            y_at_mm=effective_y_grid or None,
            member_count=primary_count,
            category="beam",
        )
    )
    joist_spacing = _mm(prompt, r"Level 1[\s\S]{0,500}?every\s*(\d+(?:\.\d+)?)\s*mm") or 1000.0
    groups.append(
        StructuralGroupSpec(
            id="level1_joists",
            profile_name=_profile_after(prompt, r"Level 1[\s\S]{0,500}?IPE180", "IPE180"),
            orientation="horizontal_y",
            assigned_to_grid="distributed_along_x",
            start_level="Level1",
            end_level="Level1",
            spacing_mm=float(joist_spacing),
            x_max_mm=level1_span[1],
            category="beam",
        )
    )

    if any(level.name == "Level2" for level in levels):
        level2_span = spans.get(2, (float(length) / 2.0, float(length)))
        level2_y_min, level2_y_max = _level2_deck_y_bounds(prompt)
        guardrail_level = next((level.name for level in levels if level.name == "Guardrail"), None)
        groups.append(
            StructuralGroupSpec(
                id="level2_cantilevers",
                profile_name=_profile_after(prompt, r"Level 2[\s\S]{0,500}?Cantilever Beams", "IPE500"),
                orientation="horizontal_y",
                assigned_to_grid="along_y_per_x_station",
                start_level="Level2",
                end_level="Level2",
                x_min_mm=level2_span[0],
                x_max_mm=level2_span[1],
                y_from_mm=y_spine,
                y_to_mm=y_float,
                category="beam",
            )
        )
        groups.append(
            StructuralGroupSpec(
                id="level2_hangers",
                profile_name=_profile_after(prompt, r"TENSION\s+HANGER|Hanger Rods", "CHS89x6"),
                orientation="diagonal_plan",
                assigned_to_grid="per_x_station",
                start_level=column_top,
                end_level="Level2",
                x_min_mm=level2_span[0],
                x_max_mm=level2_span[1],
                y_from_mm=y_spine,
                y_to_mm=y_float,
                category="brace",
            )
        )
        joist_spacing_l2 = (
            _mm(
                prompt,
                r"Level 2[\s\S]{0,500}?Secondary Joists[\s\S]{0,200}?every\s*(\d+(?:\.\d+)?)\s*mm",
            )
            or _mm(prompt, r"Secondary Joists[\s\S]{0,200}?every\s*(\d+(?:\.\d+)?)\s*mm across")
            or 600.0
        )
        groups.append(
            StructuralGroupSpec(
                id="level2_joists",
                profile_name=_profile_after(prompt, r"Level 2[\s\S]{0,500}?Secondary Joists", "IPE140"),
                orientation="horizontal_x",
                assigned_to_grid="distributed_along_y",
                start_level="Level2",
                end_level="Level2",
                spacing_mm=float(joist_spacing_l2),
                x_min_mm=level2_span[0],
                x_max_mm=level2_span[1],
                y_min_mm=level2_y_min,
                y_max_mm=level2_y_max,
                category="beam",
            )
        )
        if guardrail_level:
            guard_profile = _profile_after(prompt, r"SAFETY GUARDRAILS|GUARDRAIL", "RHS50x50x4")
            groups.extend(
                [
                    StructuralGroupSpec(
                        id="level2_guard_at_x_min",
                        profile_name=guard_profile,
                        orientation="horizontal_y",
                        assigned_to_grid="along_y_at_fixed_x",
                        start_level=guardrail_level,
                        end_level=guardrail_level,
                        x_min_mm=level2_span[0],
                        x_max_mm=level2_span[0],
                        y_min_mm=level2_y_min,
                        y_max_mm=level2_y_max,
                        category="beam",
                    ),
                    StructuralGroupSpec(
                        id="level2_guard_at_x_max",
                        profile_name=guard_profile,
                        orientation="horizontal_y",
                        assigned_to_grid="along_y_at_fixed_x",
                        start_level=guardrail_level,
                        end_level=guardrail_level,
                        x_min_mm=level2_span[1],
                        x_max_mm=level2_span[1],
                        y_min_mm=level2_y_min,
                        y_max_mm=level2_y_max,
                        category="beam",
                    ),
                    StructuralGroupSpec(
                        id="level2_guard_at_y_min",
                        profile_name=guard_profile,
                        orientation="horizontal_x",
                        assigned_to_grid="along_x_at_fixed_y",
                        start_level=guardrail_level,
                        end_level=guardrail_level,
                        x_min_mm=level2_span[0],
                        x_max_mm=level2_span[1],
                        y_min_mm=level2_y_min,
                        y_max_mm=level2_y_min,
                        category="beam",
                    ),
                    StructuralGroupSpec(
                        id="level2_guard_at_y_max",
                        profile_name=guard_profile,
                        orientation="horizontal_x",
                        assigned_to_grid="along_x_at_fixed_y",
                        start_level=guardrail_level,
                        end_level=guardrail_level,
                        x_min_mm=level2_span[0],
                        x_max_mm=level2_span[1],
                        y_min_mm=level2_y_max,
                        y_max_mm=level2_y_max,
                        category="beam",
                    ),
                ]
            )

    return groups


def parse_structured_prompt_to_universal_intent(prompt: str) -> UniversalStructuralIntent | None:
    prompt = _normalize_prompt_for_parsing(prompt)
    length = _mm(
        prompt,
        r"(?:Total )?(?:Structural |Cantilever )?Length[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
    )
    width = _mm(
        prompt,
        r"(?:Total )?(?:Structural |Floating )?Width[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
    )
    if width is None:
        width = _mm(prompt, r"(?:Total )?(?:Floating )?Projection[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm")
    if width is None:
        width = _mm(prompt, r"(?:Mezzanine )?Total Width[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm")
    bay = _mm(
        prompt,
        r"(?:Bay Spacing|(?:Global )?Grid Spacing)[^\n\r:]*:\s*(\d+(?:\.\d+)?)\s*mm",
    )
    if bay is None:
        bay = _mm(prompt, r"(\d+(?:\.\d+)?)\s*mm increments along the X-Axis")
    if length is None or width is None or bay is None:
        return None

    levels = _collect_levels(prompt)
    frames_along_x = int(round(float(length) / float(bay))) + 1
    y_grid = _explicit_y_grid_lines(prompt)
    if not y_grid:
        dual_grid_cols = _count(prompt, r"(?:VERTICAL|DUAL-GRID) COLUMNS[\s\S]{0,240}?(\d+)\s*Units")
        y_grid = _infer_triple_column_y_grid(
            width=float(width),
            col_count=dual_grid_cols,
            frames_along_x=frames_along_x,
        )
    grid = GridFrameSpec(
        length_x_mm=float(length),
        width_y_mm=float(width),
        bay_spacing_x_mm=float(bay),
        frame_line_y_mm=y_grid or None,
    )
    slab_t = _mm(prompt, r"Thickness\s*=\s*(\d+(?:\.\d+)?)\s*mm") or 500.0
    joist_spacing = _mm(prompt, r"every\s*(\d+(?:\.\d+)?)\s*mm along the X-axis") or 2500.0

    groups: list[StructuralGroupSpec] = []
    multi_level_groups = _groups_from_multi_level_sections(
        prompt,
        levels=levels,
        length=float(length),
        width=float(width),
        bay=float(bay),
        y_grid=y_grid,
    )
    if multi_level_groups:
        groups = multi_level_groups
        groups.extend(_roof_groups(prompt, levels))
        groups.extend(_roof_brace_groups(prompt, levels))
        groups.extend(_wall_brace_groups(prompt, levels))

    col_count: int | None = None
    deck_top = next((level.name for level in levels if level.name == "DeckTop"), None)
    if not multi_level_groups:
        col_count = _count(prompt, r"MAIN STRUCTURAL COLUMNS[\s\S]{0,160}?(\d+)\s*Units")
    if not multi_level_groups and col_count is None:
        col_count = _count(prompt, r"SUPPORT COLUMNS[\s\S]{0,160}?-\s*(\d+)\s*Units")
    if not multi_level_groups and col_count is None:
        front = re.search(r"(\d+)\s+columns?\s+along\s+the\s+front", prompt, re.IGNORECASE)
        back = re.search(r"(\d+)\s+matching\s+columns?\s+along\s+the\s+back", prompt, re.IGNORECASE)
        if front and back:
            col_count = int(front.group(1)) + int(back.group(1))
    if not multi_level_groups and col_count is None and re.search(
        r"MAIN COLUMNS|MAIN STRUCTURAL COLUMNS", prompt, re.IGNORECASE
    ):
        col_count = frames_along_x * 2
    if not multi_level_groups and col_count is None:
        rear_line = re.search(
            r"(\d+)\s+columns?\s+strictly along[^\n]{0,80}Y\s*=\s*0",
            prompt,
            re.IGNORECASE,
        )
        if rear_line:
            col_count = int(rear_line.group(1))

    column_grid = "all_frame_lines"
    if not multi_level_groups and col_count is not None and col_count == frames_along_x:
        column_grid = "along_all_x_at_y_min"

    if not multi_level_groups and col_count is not None:
        top_level = _column_top_level(levels)
        if any(level.name == "UpperAnchor" for level in levels):
            top_level = "UpperAnchor"
        groups.append(
            StructuralGroupSpec(
                id="main_columns",
                profile_name=_profile_after(
                    prompt,
                    r"REAR ANCHOR COLUMNS|MAIN STRUCTURAL COLUMNS|MAIN COLUMNS|SUPPORT COLUMNS",
                    "HEB200",
                ),
                orientation="vertical",
                assigned_to_grid=column_grid,
                start_level="Ground",
                end_level=top_level,
                member_count=col_count,
                category="column",
            )
        )

    if not multi_level_groups:
        primary_profile = _profile_after(prompt, r"Primary Beams|MAIN GIRDERS", "HEB300")
        joist_profile = _profile_after(prompt, r"Secondary Joists|FLOOR JOISTS", "IPE180")

        for level in levels:
            if not level.name.startswith("Floor"):
                continue
            prefix = level.name.lower()
            groups.extend(
                _floor_framing_groups(
                    prefix=prefix,
                    level=level.name,
                    primary_profile=primary_profile,
                    joist_profile=joist_profile,
                    joist_spacing_mm=float(joist_spacing),
                )
            )

        primary_count = _count(prompt, r"MAIN GIRDERS[\s\S]{0,160}?-\s*(\d+)\s*Units")
        deck_top = next((level.name for level in levels if level.name == "DeckTop"), None)
        if primary_count is not None and deck_top:
            groups.append(
                StructuralGroupSpec(
                    id="primary_girders_x",
                    profile_name=primary_profile,
                    orientation="horizontal_x",
                    assigned_to_grid="along_x_between_columns",
                    start_level=deck_top,
                    end_level=deck_top,
                    member_count=max(0, primary_count - 2),
                    category="beam",
                )
            )
            groups.append(
                StructuralGroupSpec(
                    id="primary_girders_y",
                    profile_name=primary_profile,
                    orientation="horizontal_y",
                    assigned_to_grid="along_y_at_frame_ends",
                    start_level=deck_top,
                    end_level=deck_top,
                    member_count=2,
                    category="beam",
                )
            )

        deck_level_name = next(
            (level.name for level in levels if level.name in ("Deck", "DeckTop")),
            None,
        )
        joist_count = _count(prompt, r"FLOOR JOISTS[\s\S]{0,160}?-\s*(\d+)\s*Lines")
        if joist_count is not None and deck_level_name:
            joist_along_x = bool(
                re.search(
                    r"(?:JOISTS|joists)[\s\S]{0,320}?along the X-axis",
                    prompt,
                    re.IGNORECASE,
                )
            )
            groups.append(
                StructuralGroupSpec(
                    id="floor_joists",
                    profile_name=joist_profile,
                    orientation="horizontal_y" if joist_along_x else "horizontal_x",
                    assigned_to_grid="distributed_along_x" if joist_along_x else "distributed_along_y",
                    start_level=deck_level_name,
                    end_level=deck_level_name,
                    spacing_mm=joist_spacing or (float(length) / max(1, joist_count - 1)),
                    member_count=joist_count,
                    category="beam",
                )
            )

        brace_count = _count(prompt, r"KNEE BRACES[\s\S]{0,160}?Add\s*(\d+)\s*diagonal")
        if brace_count is not None and any(level.name == "BraceStart" for level in levels):
            groups.append(
                StructuralGroupSpec(
                    id="knee_braces",
                    profile_name="RHS80x80x5",
                    orientation="diagonal_plan",
                    assigned_to_grid="corner_braces",
                    start_level="BraceStart",
                    end_level=_column_top_level(levels),
                    member_count=brace_count,
                    brace_offset_x_mm=1000.0,
                    category="brace",
                )
            )

        groups.extend(_roof_groups(prompt, levels))
        groups.extend(_wall_brace_groups(prompt, levels))

    quantity_groups = _groups_from_quantity_sections(prompt, levels=levels, width_mm=float(width))
    quantity_is_complete_mezzanine = (
        len(quantity_groups) >= 5
        and any(group.id == "beams_along_y_per_x" for group in quantity_groups)
        and any(group.id == "diagonals_per_x" for group in quantity_groups)
    )
    if quantity_is_complete_mezzanine and not multi_level_groups:
        groups = quantity_groups
    elif quantity_groups and not multi_level_groups:
        existing_ids = {group.id for group in groups}
        legacy_ids = {group.id for group in groups}

        def _has_legacy(*prefixes: str) -> bool:
            return any(
                any(legacy_id == prefix or legacy_id.startswith(f"{prefix}_") for legacy_id in legacy_ids)
                for prefix in prefixes
            )

        skip_when_legacy = {
            "columns_along_y_min": ("main_columns",),
            "beams_along_y_per_x": ("primary_girders", "beams_along_y"),
            "joists_along_x_spaced_y": ("floor_joists",),
            "diagonals_per_x": ("knee_braces", "wall_brace"),
        }
        for group in quantity_groups:
            legacy_prefixes = skip_when_legacy.get(group.id, ())
            if legacy_prefixes and _has_legacy(*legacy_prefixes):
                continue
            if group.id not in existing_ids:
                groups.append(group)

    slabs: list[SlabGroupSpec] = []
    if re.search(r"HEAVY CONCRETE FOUNDATION|foundation slab", prompt, re.IGNORECASE):
        foundation_t = _mm(prompt, r"FOUNDATION[\s\S]{0,200}?Thickness\s*=\s*(\d+(?:\.\d+)?)\s*mm") or float(
            slab_t
        )
        slabs.append(
            SlabGroupSpec(
                id="foundation_slab",
                top_level="Ground",
                thickness_mm=float(foundation_t),
                footprint="full_grid",
            )
        )
    if any(level.name == "Level1" for level in levels):
        deck_t = _mm(prompt, r"Level 1[\s\S]{0,400}?Floor Deck[\s\S]{0,80}?(\d+(?:\.\d+)?)\s*mm")
        if deck_t is None:
            deck_t = _mm(prompt, r"Floor Deck[\s\S]{0,80}?(\d+(?:\.\d+)?)\s*mm thickness") or 50.0
        level1_x = _level_x_spans(prompt).get(1, (0.0, float(length) / 2.0))
        slabs.append(
            SlabGroupSpec(
                id="level1_deck_slab",
                top_level="Level1",
                thickness_mm=float(deck_t),
                footprint="partial_xy",
                x_min_mm=level1_x[0],
                x_max_mm=level1_x[1],
                y_min_mm=0.0,
                y_max_mm=float(width),
            )
        )
    if any(level.name == "Level2" for level in levels):
        level2_x = _level_x_spans(prompt).get(2, (float(length) / 2.0, float(length)))
        level2_y_min, level2_y_max = _level2_deck_y_bounds(prompt)
        deck_t_l2 = _mm(prompt, r"Level 2[\s\S]{0,400}?(\d+(?:\.\d+)?)\s*mm thickness") or 50.0
        slabs.append(
            SlabGroupSpec(
                id="level2_deck_slab",
                top_level="Level2",
                thickness_mm=float(deck_t_l2),
                footprint="partial_xy",
                x_min_mm=level2_x[0],
                x_max_mm=level2_x[1],
                y_min_mm=level2_y_min,
                y_max_mm=level2_y_max,
            )
        )

    _append_generic_deck_slabs(prompt, levels, slab_t=float(slab_t), slabs=slabs)

    if not groups:
        return None
    return UniversalStructuralIntent(levels=levels, grid=grid, groups=groups, slabs=slabs)

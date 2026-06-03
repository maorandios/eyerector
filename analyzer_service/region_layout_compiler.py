"""Compile region analysis with explicit grid/column coordinates → PureStructuralModelSpec."""

from __future__ import annotations

import re

from analyzer_service.region_analysis_schemas import (
    ActiveColumnIntersection,
    ColumnMarkProfile,
    ColumnPlacement,
    LayoutMode,
    RegionStructuralAnalysis,
)
from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec

JsonValue = str | int | float | bool | list[str]

MAX_GRID_LINES_PER_AXIS = 48
MAX_COLUMNS_FROM_GRID = 400
STATION_TOL_MM = 1.0


def _parse_mm_list(value: JsonValue | None) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[float] = []
        for item in value:
            out.extend(_parse_mm_list(item))
        return out
    if isinstance(value, (int, float)):
        return [float(value)]
    text = str(value).strip()
    if not text:
        return []
    parts = re.split(r"[,;\s]+", text)
    positions: list[float] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            positions.append(float(part.replace(",", "")))
        except ValueError:
            continue
    return positions


def _parse_ordered_mm_list(value: JsonValue | None) -> list[float]:
    """Parse comma-separated stations preserving blueprint order (no sort)."""
    return _parse_mm_list(value)


def _coerce_height_mm(value: float) -> float:
    """Vision sometimes returns meters (6) instead of mm (6000)."""
    if value <= 0:
        return 6000.0
    if value < 100.0:
        return value * 1000.0
    return value


_MARK_KEY_RE = re.compile(r"^(?:column_)?(C\d+)(?:_profile)?$", re.IGNORECASE)


def _positions_from_bay_spacings(bays: list[float]) -> list[float]:
    positive = [float(b) for b in bays if float(b) > 1.0]
    if not positive:
        return []
    cumulative = [0.0]
    for bay in positive:
        cumulative.append(cumulative[-1] + bay)
    return cumulative


def _dedupe_sort(values: list[float]) -> list[float]:
    """Rule 1: remove duplicates, sort ascending."""
    if not values:
        return []
    cleaned = sorted({max(0.0, float(v)) for v in values})
    out: list[float] = []
    for v in cleaned:
        if not out or v - out[-1] > STATION_TOL_MM:
            out.append(v)
    return out


def _is_strictly_cumulative(stations: list[float]) -> bool:
    """Absolute stations: start at 0, each step strictly increasing."""
    if len(stations) < 2:
        return False
    if stations[0] > STATION_TOL_MM:
        return False
    return all(stations[i] > stations[i - 1] + STATION_TOL_MM for i in range(1, len(stations)))


def _strictly_increasing_subsequence(values: list[float]) -> list[float]:
    """Drop vision noise that breaks monotonicity."""
    seq = _dedupe_sort(values)
    if not seq:
        return []
    out = [seq[0]]
    for v in seq[1:]:
        if v > out[-1] + STATION_TOL_MM:
            out.append(v)
    return out


def _normalize_axis_positions(values: list[float]) -> list[float]:
    """
    Rule 2: absolute stations OR bay widths — never both in one pass.
    """
    seq = _dedupe_sort(values)
    if len(seq) < 2:
        return seq[:MAX_GRID_LINES_PER_AXIS]

    if seq[0] <= STATION_TOL_MM:
        stations = _strictly_increasing_subsequence(seq)
        if len(stations) >= 2:
            return stations[:MAX_GRID_LINES_PER_AXIS]

    bays = [v for v in seq if v > STATION_TOL_MM]
    if len(bays) >= 2:
        cumulative = _positions_from_bay_spacings(bays)
        if len(cumulative) >= 2:
            return cumulative[:MAX_GRID_LINES_PER_AXIS]

    return seq[:MAX_GRID_LINES_PER_AXIS]


def _best_axis_candidate(*candidate_lists: list[float]) -> list[float]:
    """Pick longest valid cumulative station list; do not merge unlike types."""
    normalized = [_normalize_axis_positions(list(c)) for c in candidate_lists if c]
    valid = [n for n in normalized if len(n) >= 2 and _is_strictly_cumulative(n)]
    if valid:
        return max(valid, key=len)[:MAX_GRID_LINES_PER_AXIS]
    if normalized:
        return max(normalized, key=len)[:MAX_GRID_LINES_PER_AXIS]
    return []


def _collect_axis_raw_candidates(
    params: dict[str, JsonValue],
    *,
    axis: str,
    array_field: list[float],
    bay_field: list[float],
) -> tuple[list[list[float]], list[list[float]]]:
    """Station lists (grid lines) vs bay-width chains — never union bays into stations."""
    station_candidates: list[list[float]] = []
    bay_candidates: list[list[float]] = []

    for key in (f"grid_lines_{axis}_mm", f"{axis}_grid_positions_mm", f"grid_{axis}_mm"):
        if key in params:
            ordered = _parse_ordered_mm_list(params[key])
            if ordered:
                station_candidates.append(ordered)

    if array_field:
        station_candidates.append(list(array_field))

    parsed_bays: list[float] = list(bay_field)
    for key in (f"{axis}_bay_spacings_mm", f"bay_spacings_{axis}_mm", f"bays_{axis}_mm"):
        if key in params:
            parsed_bays.extend(_parse_mm_list(params[key]))
    for key, val in params.items():
        key_l = str(key).lower()
        if axis in key_l and "bay" in key_l:
            parsed_bays.extend(_parse_mm_list(val))
    if parsed_bays:
        bay_candidates.append(parsed_bays)

    return station_candidates, bay_candidates


def _resolve_axis_stations(
    station_candidates: list[list[float]],
    bay_candidates: list[list[float]],
) -> list[float]:
    """
    Prefer the longest valid cumulative station list from grid-line sources.
    Bay chains only expand sparse [0, total] endpoints — not merged into the union.
    """
    bays_flat = [float(v) for group in bay_candidates for v in group]

    if not station_candidates:
        if len(bays_flat) >= 2:
            return _normalize_axis_positions(_positions_from_bay_spacings(bays_flat))
        return []

    normalized_sources = [_normalize_axis_positions(list(c)) for c in station_candidates if c]
    merged_raw: list[float] = []
    for c in station_candidates:
        merged_raw.extend(float(v) for v in c)
    union = _normalize_axis_positions(merged_raw)
    stations = _best_axis_candidate(union, *normalized_sources)
    return _expand_sparse_axis(stations, bays_flat)


def _expand_sparse_axis(stations: list[float], bays: list[float]) -> list[float]:
    """Rebuild from bay chain when vision only returned endpoints (0 and far edge)."""
    if len(stations) >= 3:
        return stations
    positive_bays = [float(b) for b in bays if float(b) > STATION_TOL_MM]
    if len(positive_bays) < 2:
        return stations
    from_bays = _normalize_axis_positions(_positions_from_bay_spacings(positive_bays))
    if len(from_bays) >= 3 and len(from_bays) > len(stations):
        return from_bays
    if len(stations) >= 2 and len(from_bays) >= 2:
        return _best_axis_candidate(stations, from_bays)
    return stations if len(stations) >= 2 else from_bays


def _axis_positions_from_params(
    params: dict[str, JsonValue],
    *,
    axis: str,
    array_field: list[float],
    bay_field: list[float],
) -> list[float]:
    station_cands, bay_cands = _collect_axis_raw_candidates(
        params, axis=axis, array_field=array_field, bay_field=bay_field
    )
    stations = _resolve_axis_stations(station_cands, bay_cands)
    if len(stations) < 2:
        return []
    return stations[:MAX_GRID_LINES_PER_AXIS]


def _positions_from_analysis(
    analysis: RegionStructuralAnalysis,
    overrides: dict[str, JsonValue] | None,
) -> tuple[list[float], list[float]]:
    params = analysis.parameters_dict()
    if overrides:
        params = {**params, **overrides}

    xs = _axis_positions_from_params(
        params,
        axis="x",
        array_field=analysis.x_grid_positions_mm,
        bay_field=analysis.x_bay_spacings_mm,
    )
    ys = _axis_positions_from_params(
        params,
        axis="y",
        array_field=analysis.y_grid_positions_mm,
        bay_field=analysis.y_bay_spacings_mm,
    )
    return xs, ys


def _snap_station(value: float, stations: list[float], tol: float = STATION_TOL_MM) -> float | None:
    if not stations:
        return float(value)
    best = min(stations, key=lambda s: abs(s - value))
    if abs(best - value) <= tol:
        return float(best)
    return None


def _mark_profile_map(analysis: RegionStructuralAnalysis) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in analysis.column_profile_by_mark:
        mark = entry.mark.strip()
        profile = entry.profile_name.strip()
        if mark and profile:
            out[mark.upper()] = profile
    return out


def _clean_profile_token(raw: str) -> str:
    """Use first catalog token when vision bundles plate + section (e.g. RHS100X100X5 PLT10*200)."""
    return str(raw).strip().split()[0] if str(raw).strip() else ""


def _resolve_profile_for_column(
    *,
    mark: str | None,
    per_col_profile: str | None,
    mark_map: dict[str, str],
    default_profile: str,
) -> str:
    if per_col_profile and str(per_col_profile).strip():
        return _clean_profile_token(str(per_col_profile))
    if mark:
        mapped = mark_map.get(mark.strip().upper())
        if mapped:
            return mapped
    return default_profile


def _normalize_profile_name(profile: str) -> str:
    try:
        from analyzer_service.steel_catalog import normalize_profile_name

        return normalize_profile_name(profile) or profile
    except Exception:
        return profile


def _nearest_grid_index(value: float, stations: list[float]) -> int:
    return min(range(len(stations)), key=lambda i: abs(stations[i] - value))


def _placements_from_active_intersections(
    xs: list[float],
    ys: list[float],
    intersections: list[ActiveColumnIntersection],
    *,
    mark_map: dict[str, str],
    default_profile: str,
    default_height: float,
) -> list[ColumnPlacement]:
    """Resolve sparse columns via grid_index_x/y into xs[] and ys[] station arrays."""
    if len(xs) < 2 or len(ys) < 2:
        return []

    placements: list[ColumnPlacement] = []
    seen: set[tuple[int, int]] = set()

    for entry in intersections:
        if len(placements) >= MAX_COLUMNS_FROM_GRID:
            break

        ix = int(entry.grid_index_x)
        iy = int(entry.grid_index_y)
        if ix < 0 or ix >= len(xs) or iy < 0 or iy >= len(ys):
            continue

        key = (ix, iy)
        if key in seen:
            continue
        seen.add(key)

        x_mm = float(xs[ix])
        y_mm = float(ys[iy])
        profile = _normalize_profile_name(
            _resolve_profile_for_column(
                mark=entry.mark,
                per_col_profile=entry.profile_name,
                mark_map=mark_map,
                default_profile=default_profile,
            )
        )
        # IFC ids must be unique; the same mark (e.g. C1) can appear at multiple grid points.
        col_id = f"col_{ix}_{iy}"

        placements.append(
            ColumnPlacement(
                id=col_id,
                x_mm=x_mm,
                y_mm=y_mm,
                profile_name=profile,
                height_mm=default_height,
                mark=entry.mark,
            )
        )
    return placements


def _uses_sparse_placement(analysis: RegionStructuralAnalysis) -> bool:
    return (
        analysis.layout_mode == "sparse_intersections"
        or len(analysis.active_column_intersections) >= 1
    )


def _profiles_from_params(params: dict[str, JsonValue]) -> dict[str, str]:
    """Read C1/C14 → profile from detected_parameters / form overrides."""
    out: dict[str, str] = {}
    for key, val in params.items():
        if val is None:
            continue
        m = _MARK_KEY_RE.match(str(key).strip())
        if not m:
            continue
        profile = str(val).strip()
        if profile and not profile.replace(".", "", 1).isdigit():
            out[m.group(1).upper()] = _clean_profile_token(profile)
    return out


def _layout_mode_from_params(params: dict[str, JsonValue]) -> str | None:
    raw = params.get("layout_mode")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in ("sparse_intersections", "sparse"):
        return "sparse_intersections"
    if text in ("dense_matrix", "dense"):
        return "dense_matrix"
    return None


def _placements_to_active_intersections(
    placements: list[ColumnPlacement],
    xs: list[float],
    ys: list[float],
) -> list[ActiveColumnIntersection]:
    """Convert legacy explicit mm placements to grid indices for sparse mode."""
    if len(xs) < 2 or len(ys) < 2:
        return []
    out: list[ActiveColumnIntersection] = []
    seen: set[tuple[int, int]] = set()
    for col in placements:
        ix = _nearest_grid_index(col.x_mm, xs)
        iy = _nearest_grid_index(col.y_mm, ys)
        if (ix, iy) in seen:
            continue
        seen.add((ix, iy))
        mark = col.mark or (col.id if col.id.upper().startswith("C") else None)
        default_applied = col.profile_name
        out.append(
            ActiveColumnIntersection(
                grid_index_x=ix,
                grid_index_y=iy,
                mark=mark,
                profile_name=default_applied,
            )
        )
    return out


def hydrate_analysis_for_compile(
    analysis: RegionStructuralAnalysis,
    overrides: dict[str, JsonValue] | None = None,
) -> RegionStructuralAnalysis:
    """
    Merge form/vision detected_parameters into structured fields before placement.
    Keeps UI-edited grid_lines and per-mark profiles aligned with the compiler.
    """
    params = analysis.parameters_dict()
    if overrides:
        params = {**params, **overrides}

    mark_map = _mark_profile_map(analysis)
    mark_map.update(_profiles_from_params(params))
    profile_entries = [
        ColumnMarkProfile(mark=k, profile_name=v) for k, v in sorted(mark_map.items())
    ]

    layout_mode: LayoutMode = analysis.layout_mode
    mode_param = _layout_mode_from_params(params)
    if mode_param:
        layout_mode = mode_param  # type: ignore[assignment]

    xs = _axis_positions_from_params(
        params,
        axis="x",
        array_field=analysis.x_grid_positions_mm,
        bay_field=analysis.x_bay_spacings_mm,
    )
    ys = _axis_positions_from_params(
        params,
        axis="y",
        array_field=analysis.y_grid_positions_mm,
        bay_field=analysis.y_bay_spacings_mm,
    )

    active = list(analysis.active_column_intersections)
    if not active and analysis.column_placements and (
        layout_mode == "sparse_intersections" or mode_param == "sparse_intersections"
    ):
        active = _placements_to_active_intersections(analysis.column_placements, xs, ys)
    params_source = str(params.get("grid_extraction_source") or "")
    keep_explicit_placements = (
        layout_mode == "dense_matrix"
        and analysis.column_placements
        and (
            "column_clicks_exact" in params_source
            or "column_clicks_vector_snap" in params_source
            or "column_clicks_pdf_grid_snap" in params_source
        )
    )
    if (
        not active
        and analysis.column_placements
        and len(xs) >= 2
        and len(ys) >= 2
        and len(analysis.column_placements) < len(xs) * len(ys)
        and not keep_explicit_placements
    ):
        layout_mode = "sparse_intersections"
        active = _placements_to_active_intersections(analysis.column_placements, xs, ys)

    return analysis.model_copy(
        update={
            "column_profile_by_mark": profile_entries,
            "layout_mode": layout_mode,
            "active_column_intersections": active,
            "x_grid_positions_mm": xs if len(xs) >= 2 else analysis.x_grid_positions_mm,
            "y_grid_positions_mm": ys if len(ys) >= 2 else analysis.y_grid_positions_mm,
        }
    )


def enrich_region_grid_analysis(analysis: RegionStructuralAnalysis) -> RegionStructuralAnalysis:
    """Merge vision arrays + detected_parameters text into sorted cumulative grid lines."""
    xs, ys = _positions_from_analysis(analysis, None)
    if len(xs) < 2 and len(ys) < 2:
        return analysis

    from analyzer_service.region_analysis_schemas import DetectedParameterEntry

    x_text = ", ".join(str(int(v)) if v == int(v) else str(round(v, 1)) for v in xs)
    y_text = ", ".join(str(int(v)) if v == int(v) else str(round(v, 1)) for v in ys)
    skip = {"grid_lines_x_mm", "grid_lines_y_mm"}
    entries = [e for e in analysis.detected_parameters if e.key not in skip]
    entries.append(DetectedParameterEntry(key="grid_lines_x_mm", value=x_text))
    entries.append(DetectedParameterEntry(key="grid_lines_y_mm", value=y_text))

    return analysis.model_copy(
        update={
            "x_grid_positions_mm": xs,
            "y_grid_positions_mm": ys,
            "detected_parameters": entries,
        }
    )


def resolve_column_placements(
    analysis: RegionStructuralAnalysis,
    overrides: dict[str, JsonValue] | None = None,
) -> list[ColumnPlacement]:
    analysis = hydrate_analysis_for_compile(analysis, overrides)
    analysis = enrich_region_grid_analysis(analysis)

    params = analysis.parameters_dict()
    if overrides:
        params = {**params, **overrides}

    profile = str(params.get("column_profile") or "HEB200").strip() or "HEB200"
    height = 6000.0
    for key in ("eave_height_mm", "column_height_mm", "height_mm"):
        if key in params:
            try:
                height = _coerce_height_mm(float(params[key]))
                break
            except (TypeError, ValueError):
                pass

    xs, ys = _positions_from_analysis(analysis, overrides)
    mark_map = _mark_profile_map(analysis)
    default_profile = _normalize_profile_name(profile)

    if _uses_sparse_placement(analysis):
        sparse = _placements_from_active_intersections(
            xs,
            ys,
            analysis.active_column_intersections,
            mark_map=mark_map,
            default_profile=default_profile,
            default_height=height,
        )
        if sparse:
            return sparse

    if len(xs) < 2 or len(ys) < 2:
        if analysis.column_placements:
            return list(analysis.column_placements)
        return []

    if analysis.column_placements and not _uses_sparse_placement(analysis):
        out: list[ColumnPlacement] = []
        for col in analysis.column_placements:
            mark = col.mark or (col.id if col.id.upper().startswith("C") else None)
            prof = _normalize_profile_name(
                _resolve_profile_for_column(
                    mark=mark,
                    per_col_profile=col.profile_name,
                    mark_map=mark_map,
                    default_profile=default_profile,
                )
            )
            out.append(
                col.model_copy(
                    update={
                        "profile_name": prof,
                        "height_mm": _coerce_height_mm(float(col.height_mm)),
                    }
                )
            )
        return out

    if len(xs) >= 2 and len(ys) >= 2:
        placements: list[ColumnPlacement] = []
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                if len(placements) >= MAX_COLUMNS_FROM_GRID:
                    return placements
                placements.append(
                    ColumnPlacement(
                        id=f"col_{i}_{j}",
                        x_mm=float(x),
                        y_mm=float(y),
                        profile_name=default_profile,
                        height_mm=height,
                    )
                )
        return placements
    return []


def uses_explicit_layout(analysis: RegionStructuralAnalysis) -> bool:
    if _uses_sparse_placement(analysis):
        return True
    if analysis.column_placements:
        return True
    xs, ys = _positions_from_analysis(analysis, None)
    return len(xs) >= 2 and len(ys) >= 2


def _unique_placement_element_id(col: ColumnPlacement, used: set[str]) -> str:
    """Ensure PureStructuralModelSpec element ids are unique (marks may repeat)."""
    base = (col.id or "").strip() or f"col_{int(col.x_mm)}_{int(col.y_mm)}"
    if base not in used:
        used.add(base)
        return base
    candidate = f"{base}_{int(col.x_mm)}_{int(col.y_mm)}"
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def map_region_analysis_to_pure_model(
    analysis: RegionStructuralAnalysis,
    overrides: dict[str, JsonValue] | None = None,
) -> PureStructuralModelSpec | None:
    placements = resolve_column_placements(analysis, overrides)
    if not placements:
        return None

    used_ids: set[str] = set()
    elements = [
        PureSteelElementSpec(
            id=_unique_placement_element_id(col, used_ids),
            profile_name=col.profile_name,
            start_x=col.x_mm,
            start_y=col.y_mm,
            start_z=0.0,
            end_x=col.x_mm,
            end_y=col.y_mm,
            end_z=col.height_mm,
            up_vector_z=1.0,
        )
        for col in placements
    ]
    return PureStructuralModelSpec(elements=elements, slabs=None)

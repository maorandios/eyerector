"""Normalize LLM grid assignment strings to supported geometric placement rules."""

from __future__ import annotations

from typing import Any

# Canonical vertical column placements
VERTICAL_ALL_GRID = frozenset({"all_frame_lines", "all_frames"})
VERTICAL_PERIMETER = frozenset({"perimeter"})
VERTICAL_ALONG_X_AT_Y_MIN = frozenset(
    {
        "along_all_x_at_y_min",
        "along_x_at_y_min",
        "all_x_at_y_min",
    }
)
VERTICAL_ALONG_X_AT_Y_MAX = frozenset(
    {
        "along_all_x_at_y_max",
        "along_x_at_y_max",
        "all_x_at_y_max",
    }
)

# Tokens in assignment strings that imply a single grid Y line (no architectural meaning)
_Y_MIN_TOKENS = ("y_min", "y0", "y_0", "grid_y0", "min_y", "origin_y", "anchor_line", "support_line")
_Y_MAX_TOKENS = ("y_max", "y1", "front_edge", "max_y")


def normalize_structural_group_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Map legacy warren_web_per_frame to all_frame_lines; Warren layout uses group id."""
    assign = data.get("assigned_to_grid")
    if not isinstance(assign, str):
        return data
    key = assign.strip().casefold().replace("-", "_")
    if key != "warren_web_per_frame":
        return data
    out = dict(data)
    gid = str(out.get("id") or "web_members")
    if "warren" not in gid.casefold():
        out["id"] = f"{gid}_warren" if gid else "web_members_warren"
    out["assigned_to_grid"] = "all_frame_lines"
    return out


def normalize_universal_intent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    groups = payload.get("groups")
    if not isinstance(groups, list):
        return payload
    normalized = [
        normalize_structural_group_dict(item) if isinstance(item, dict) else item for item in groups
    ]
    return {**payload, "groups": normalized}


def coerce_vertical_assignment(assigned_to_grid: str) -> str:
    raw = assigned_to_grid.strip()
    key = raw.casefold().replace("-", "_").replace(" ", "_")
    if key in VERTICAL_ALL_GRID:
        return "all_frame_lines"
    if key in VERTICAL_PERIMETER:
        return "perimeter"
    if key in VERTICAL_ALONG_X_AT_Y_MIN:
        return "along_all_x_at_y_min"
    if key in VERTICAL_ALONG_X_AT_Y_MAX:
        return "along_all_x_at_y_max"
    if any(token in key for token in _Y_MIN_TOKENS):
        return "along_all_x_at_y_min"
    if "anchor" in key and "upper" not in key and "ridge" not in key:
        return "along_all_x_at_y_min"
    if any(token in key for token in _Y_MAX_TOKENS):
        return "along_all_x_at_y_max"
    # Common LLM pattern: one support line at minimum Y, columns at every X station
    if key.startswith("along_y") and "between" not in key and "frame_end" not in key:
        return "along_all_x_at_y_min"
    if key.startswith("along_x") and "between" not in key:
        return "along_all_x_at_y_min"
    if "single" in key and "line" in key:
        return "along_all_x_at_y_min"
    return raw


def coerce_horizontal_y_assignment(assigned_to_grid: str) -> str:
    key = assigned_to_grid.strip().casefold().replace("-", "_")
    if key in (
        "along_y_at_frame_ends",
        "along_y_per_frame_line",
        "distributed_along_x",
        "along_y_at_x_min",
        "along_y_at_x_max",
        "along_y_at_fixed_x",
    ):
        return key
    if key in ("along_y_per_x", "per_x_station", "each_x_station", "all_x_stations"):
        return "along_y_per_x_station"
    if "per_frame" in key or "each_frame" in key:
        return "along_y_per_x_station"
    if "x_min" in key or key.endswith("_at_x0"):
        return "along_y_at_x_min"
    if "x_max" in key:
        return "along_y_at_x_max"
    if "grid_line" in key or "grid_y" in key:
        return "along_y_per_x_station"
    return assigned_to_grid


def coerce_horizontal_x_assignment(assigned_to_grid: str) -> str:
    key = assigned_to_grid.strip().casefold().replace("-", "_")
    if key in ("along_x_between_columns", "along_x_at_each_y_line", "along_x_at_fixed_y"):
        return key
    if "between_column" in key or ("along_x" in key and "grid" in key):
        return "along_x_between_columns"
    if "grid_line" in key and ("y0" in key or "y_" in key or "multi" in key):
        return "along_x_at_each_y_line"
    if key in ("distributed_along_y", "along_y_distribution", "spaced_along_y"):
        return "distributed_along_y"
    if key in ("along_x_at_y_max", "at_y_max", "along_y_max"):
        return "along_x_at_y_max"
    if key in ("along_x_at_fixed_y", "at_fixed_y", "along_y_at_y"):
        return "along_x_at_fixed_y"
    if key in ("all_frame_lines", "all_frames", "distributed_along_x", "perimeter"):
        return "along_x_between_columns"
    return assigned_to_grid


def coerce_diagonal_assignment(assigned_to_grid: str) -> str:
    key = assigned_to_grid.strip().casefold().replace("-", "_")
    if key in ("corner_braces", "first_and_last_bay_braces", "roof_truss_diagonals"):
        return key
    if "roof" in key and "plane" in key and "brac" in key:
        return "roof_truss_diagonals"
    if key in ("per_x_station", "each_x_station", "all_x_stations", "along_all_x"):
        return "per_x_station"
    if "per_x" in key or "each_x" in key:
        return "per_x_station"
    return assigned_to_grid

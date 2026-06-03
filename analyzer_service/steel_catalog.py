"""
European steel profile catalog (mm) for chat-to-IFC.

Families and IFC shapes:
- IPE / HEA / HEB / HEM  -> I-shape   (IfcIShapeProfileDef)
- UPN / UPE              -> U-channel (IfcUShapeProfileDef)
- L                      -> angle     (IfcLShapeProfileDef)
- RHS / SHS              -> rect/square hollow (IfcRectangleHollowProfileDef)
- CHS                    -> circular hollow    (IfcCircleHollowProfileDef)

Dimensions are stored as positional lists (mm), conventions:
- I-shape: [overall_depth, overall_width, web_thickness, flange_thickness]
- U-shape: [overall_depth, flange_width, web_thickness, flange_thickness]
- L:       [depth, width, thickness]
- RHS:     [width, depth, wall_thickness]
- CHS:     [outer_diameter, wall_thickness]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

ProfileFamily = Literal["RHS", "HEA", "HEB", "HEM", "IPE", "UPN", "UPE", "L", "CHS"]
ProfileShape = Literal["I", "U", "L", "RHS", "CHS"]

_CATALOG_PATH = Path(__file__).resolve().parent / "steel_catalog.json"

I_SHAPE_FAMILIES = ("IPE", "HEA", "HEB", "HEM")
U_SHAPE_FAMILIES = ("UPN", "UPE")

# profile_type (family stored on elements) -> IFC geometry shape
PROFILE_SHAPE: dict[str, ProfileShape] = {
    **{fam: "I" for fam in I_SHAPE_FAMILIES},
    **{fam: "U" for fam in U_SHAPE_FAMILIES},
    "L": "L",
    "RHS": "RHS",
    "SHS": "RHS",
    "CHS": "CHS",
}

SHAPE_DIM_COUNT: dict[ProfileShape, int] = {"I": 4, "U": 4, "L": 3, "RHS": 3, "CHS": 2}

DEFAULT_FALLBACK_KEYS: dict[str, str] = {
    "IPE": "IPE200",
    "HEB": "HEB200",
    "HEA": "HEA200",
    "HEM": "HEM200",
    "UPN": "UPN200",
    "UPE": "UPE200",
    "L": "L100x100x10",
    "RHS": "200x200x10",
    "CHS": "168.3x5",
}


@dataclass(frozen=True)
class ResolvedProfile:
    profile_key: str
    profile_type: ProfileFamily
    dimensions: list[float]

    @property
    def shape(self) -> ProfileShape:
        return profile_shape(self.profile_type)


def profile_shape(profile_type: str) -> ProfileShape:
    return PROFILE_SHAPE.get(profile_type.upper(), "I")


def load_catalog() -> dict:
    with _CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return load_catalog()


def catalog_profile_keys() -> list[str]:
    """All canonical catalog keys across every family (for the LLM prompt index)."""
    data = _catalog()
    keys: list[str] = []
    for family in (*I_SHAPE_FAMILIES, *U_SHAPE_FAMILIES, "L", "RHS", "SHS"):
        keys.extend(sorted(data.get(family, {}).keys()))
    keys.extend(f"CHS{k}" for k in sorted(data.get("CHS", {}).keys()))
    # De-duplicate while preserving order (RHS and SHS share square keys).
    seen: set[str] = set()
    unique: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _i_shape_dimensions(entry: dict) -> list[float]:
    return [
        float(entry["overall_depth_mm"]),
        float(entry["overall_width_mm"]),
        float(entry["web_thickness_mm"]),
        float(entry["flange_thickness_mm"]),
    ]


def _u_shape_dimensions(entry: dict) -> list[float]:
    return [
        float(entry["overall_depth_mm"]),
        float(entry["flange_width_mm"]),
        float(entry["web_thickness_mm"]),
        float(entry["flange_thickness_mm"]),
    ]


def _l_dimensions(entry: dict) -> list[float]:
    return [float(entry["depth_mm"]), float(entry["width_mm"]), float(entry["thickness_mm"])]


def _rhs_dimensions(entry: dict) -> list[float]:
    return [
        float(entry["width_mm"]),
        float(entry["depth_mm"]),
        float(entry["wall_thickness_mm"]),
    ]


def _chs_dimensions(entry: dict) -> list[float]:
    return [float(entry["outer_diameter_mm"]), float(entry["wall_thickness_mm"])]


def _lookup_family_entry(family: str, key: str) -> dict | None:
    data = _catalog()
    section = data.get(family.upper())
    if not isinstance(section, dict):
        return None
    return section.get(key)


def normalize_profile_name(raw: str | None) -> str | None:
    """Map user/LLM profile text to a canonical catalog key."""
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    try:
        return resolve_profile_key(text).profile_key
    except KeyError:
        return text.upper().replace(" ", "")


def _resolve_i_shape(normalized: str) -> ResolvedProfile | None:
    for family in I_SHAPE_FAMILIES:
        if normalized.upper().startswith(family):
            key = normalized.upper()
            entry = _lookup_family_entry(family, key)
            if entry:
                return ResolvedProfile(key, family, _i_shape_dimensions(entry))  # type: ignore[arg-type]
            m = re.match(rf"^{family}(\d{{2,3}})$", key)
            if m:
                return ResolvedProfile(
                    f"{family}{int(m.group(1))}",
                    family,  # type: ignore[arg-type]
                    _approximate_i_dims(family, int(m.group(1))),
                )
    return None


def _resolve_u_shape(normalized: str) -> ResolvedProfile | None:
    for family in U_SHAPE_FAMILIES:
        if normalized.upper().startswith(family):
            key = normalized.upper()
            entry = _lookup_family_entry(family, key)
            if entry:
                return ResolvedProfile(key, family, _u_shape_dimensions(entry))  # type: ignore[arg-type]
            m = re.match(rf"^{family}(\d{{2,3}})$", key)
            if m:
                size = int(m.group(1))
                # Approximate channel from depth when size not tabulated.
                return ResolvedProfile(
                    f"{family}{size}",
                    family,  # type: ignore[arg-type]
                    [float(size), max(size * 0.35, 30), max(size * 0.05, 4), max(size * 0.08, 6)],
                )
    return None


def _resolve_angle(normalized: str) -> ResolvedProfile | None:
    m = re.match(r"^L?\s*(\d+)\s*[xX×/]\s*(\d+)\s*[xX×/]\s*(\d+(?:\.\d+)?)$", normalized.strip())
    if not normalized.upper().startswith("L") or not m:
        return None
    a, b, t = int(m.group(1)), int(m.group(2)), float(m.group(3))
    key = f"L{a}x{b}x{int(t) if t == int(t) else t}"
    entry = _lookup_family_entry("L", key)
    if entry:
        return ResolvedProfile(key, "L", _l_dimensions(entry))
    return ResolvedProfile(key, "L", [float(a), float(b), t])


def _resolve_chs(normalized: str) -> ResolvedProfile | None:
    if not normalized.upper().startswith("CHS"):
        return None
    body = normalized.upper().replace("CHS", "").strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[xX×/]\s*(\d+(?:\.\d+)?)$", body)
    if not m:
        return None
    d, t = float(m.group(1)), float(m.group(2))
    bare_key = _fmt_hollow_key(d, t)
    display_key = f"CHS{bare_key}"
    entry = _lookup_family_entry("CHS", bare_key)
    if entry:
        return ResolvedProfile(display_key, "CHS", _chs_dimensions(entry))
    return ResolvedProfile(display_key, "CHS", [d, t])


def _resolve_rect_hollow(normalized: str) -> ResolvedProfile | None:
    """Handle SHS/RHS designations and bare WxDxT (square or rectangular)."""
    text = normalized.strip()
    is_shs = text.upper().startswith("SHS")
    body = re.sub(r"^(RHS|SHS)", "", text, flags=re.IGNORECASE).strip()
    body = body.replace("×", "x").replace("/", "x")
    body = re.sub(r"\s+", "", body)
    # Vision/LLM often emits uppercase X (e.g. RHS100X100X5 from Claude).
    body = re.sub(r"[X×]", "x", body)

    # SHS shorthand "100x5" -> 100x100x5
    m2 = re.match(r"^(\d+)x(\d+(?:\.\d+)?)$", body)
    if is_shs and m2:
        a, t = int(m2.group(1)), float(m2.group(2))
        return _build_rhs(a, a, t)

    m3 = re.match(r"^(\d+)x(\d+)x(\d+(?:\.\d+)?)$", body)
    if m3:
        w, d, t = int(m3.group(1)), int(m3.group(2)), float(m3.group(3))
        return _build_rhs(w, d, t)
    return None


def _build_rhs(width: int, depth: int, wall: float) -> ResolvedProfile:
    key = f"{width}x{depth}x{int(wall) if wall == int(wall) else wall}"
    for section in ("RHS", "SHS"):
        entry = _lookup_family_entry(section, key)
        if entry:
            return ResolvedProfile(key, "RHS", _rhs_dimensions(entry))
    return ResolvedProfile(key, "RHS", [float(width), float(depth), float(wall)])


def _fmt_hollow_key(*values: float) -> str:
    parts = [str(int(v)) if v == int(v) else str(v) for v in values]
    return "x".join(parts)


def resolve_profile_key(key: str) -> ResolvedProfile:
    """Resolve a profile designation to family + positional dimensions (mm)."""
    normalized = key.strip()
    if not normalized:
        raise KeyError("empty profile key")

    aliases = _catalog().get("aliases", {})
    alias_hit = aliases.get(normalized.casefold())
    if alias_hit:
        normalized = alias_hit

    for resolver in (
        _resolve_i_shape,
        _resolve_u_shape,
        _resolve_angle,
        _resolve_chs,
        _resolve_rect_hollow,
    ):
        resolved = resolver(normalized)
        if resolved is not None:
            return resolved

    raise KeyError(f"Unknown catalog profile key: {key}")


def _approximate_i_dims(family: str, size: int) -> list[float]:
    key = f"{family.upper()}{size}"
    entry = _lookup_family_entry(family, key)
    if entry:
        return _i_shape_dimensions(entry)
    s = float(size)
    width_factor = 1.0 if family.upper() in ("HEB", "HEA", "HEM") else 0.5
    return [s, s * width_factor, max(s * 0.045, 6), max(s * 0.075, 8)]


def fallback_profile(family: str) -> ResolvedProfile:
    fam = family.upper()
    if fam not in DEFAULT_FALLBACK_KEYS:
        fam = "HEB"
    return resolve_profile_key(DEFAULT_FALLBACK_KEYS[fam])


# --- Free-text resolution -------------------------------------------------

def _iter_text_candidates(text: str) -> list[tuple[int, str]]:
    """All catalog designations mentioned in free text, with their position."""
    candidates: list[tuple[int, str]] = []

    for family in (*I_SHAPE_FAMILIES, *U_SHAPE_FAMILIES):
        for m in re.finditer(rf"\b{family}\s*(\d{{2,4}})\b", text, re.IGNORECASE):
            candidates.append((m.start(), f"{family}{m.group(1)}"))

    for m in re.finditer(r"\bL\s*(\d+)\s*[xX×/]\s*(\d+)\s*[xX×/]\s*(\d+(?:\.\d+)?)\b", text):
        candidates.append((m.start(), f"L{m.group(1)}x{m.group(2)}x{m.group(3)}"))

    for m in re.finditer(r"\bCHS\s*(\d+(?:\.\d+)?)\s*[xX×/]\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE):
        candidates.append((m.start(), f"CHS{m.group(1)}x{m.group(2)}"))

    for m in re.finditer(r"\bSHS\s*(\d+)\s*[xX×/]\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE):
        candidates.append((m.start(), f"SHS{m.group(1)}x{m.group(2)}"))

    # Hebrew shorthand for HEB
    for m in re.finditer(r"(?:חתו\s*)?חב\s*(\d{2,3})\b", text):
        candidates.append((m.start(), f"HEB{m.group(1)}"))

    # Bare or RHS-prefixed WxDxT
    for m in re.finditer(
        r"\b(?:RHS\s*)?(\d+)\s*[xX×/]\s*(\d+)\s*[xX×/]\s*(\d+(?:\.\d+)?)\b",
        text,
        re.IGNORECASE,
    ):
        # Skip if this is actually part of an L/CHS designation handled above.
        prefix = text[max(0, m.start() - 2):m.start()].upper()
        if prefix.endswith("L"):
            continue
        candidates.append((m.start(), f"{m.group(1)}x{m.group(2)}x{m.group(3)}"))

    return candidates


def resolve_from_text(text: str) -> str | None:
    """Find the first catalog key mentioned in free text."""
    if not text.strip():
        return None

    aliases = _catalog().get("aliases", {})
    lowered = text.casefold()
    for alias, target in sorted(aliases.items(), key=lambda x: -len(x[0])):
        if alias in lowered:
            return target

    candidates = _iter_text_candidates(text)
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    for _, key in candidates:
        try:
            return resolve_profile_key(key).profile_key
        except KeyError:
            continue
    return None


def resolve_from_text_for_role(text: str, role: Literal["column", "beam"]) -> str | None:
    """Resolve catalog key nearest to column/beam keywords."""
    if role == "column":
        role_re = re.compile(r"\b(?:column|columns|עמוד|עמודים)\b", re.IGNORECASE)
        other_re = re.compile(r"\b(?:beam|beams|קורה|קורות)\b", re.IGNORECASE)
    else:
        role_re = re.compile(r"\b(?:beam|beams|קורה|קורות)\b", re.IGNORECASE)
        other_re = re.compile(r"\b(?:column|columns|עמוד|עמודים)\b", re.IGNORECASE)

    role_anchors = [m.start() for m in role_re.finditer(text)]
    other_anchors = [m.start() for m in other_re.finditer(text)]
    if not role_anchors:
        return resolve_from_text(text)

    def dist(pos: int, anchors: list[int]) -> float:
        if not anchors:
            return float("inf")
        return float(min(abs(pos - a) for a in anchors))

    best: tuple[float, str] | None = None
    for pos, key in _iter_text_candidates(text):
        d_role = dist(pos, role_anchors)
        d_other = dist(pos, other_anchors)
        if d_other < d_role:
            continue
        if best is None or d_role < best[0]:
            best = (d_role, key)

    if best is not None:
        try:
            return resolve_profile_key(best[1]).profile_key
        except KeyError:
            pass
    return resolve_from_text(text)


def infer_profile_key(profile_type: str, dimensions: list[float]) -> str | None:
    """Best-effort catalog key from type + dimensions."""
    fam = profile_type.upper()
    shape = profile_shape(fam)

    if shape == "RHS" and len(dimensions) >= 3:
        w, d, t = dimensions[0], dimensions[1], dimensions[2]
        return _fmt_hollow_key(w, d, t)

    if shape == "CHS" and len(dimensions) >= 2:
        return _fmt_hollow_key(dimensions[0], dimensions[1])

    if shape == "L" and len(dimensions) >= 3:
        return f"L{int(dimensions[0])}x{int(dimensions[1])}x{int(dimensions[2])}"

    if shape in ("I", "U") and len(dimensions) >= 1:
        depth = int(round(dimensions[0]))
        key = f"{fam}{depth}"
        if _lookup_family_entry(fam, key):
            return key
        return key  # allow approximation downstream
    return None


def apply_catalog_to_element(
    *,
    profile_key: str | None,
    profile_type: str,
    dimensions: list[float],
) -> ResolvedProfile:
    if profile_key:
        try:
            return resolve_profile_key(profile_key)
        except KeyError:
            pass

    inferred = infer_profile_key(profile_type, dimensions)
    if inferred:
        try:
            return resolve_profile_key(inferred)
        except KeyError:
            pass

    if profile_type.upper() in DEFAULT_FALLBACK_KEYS:
        return fallback_profile(profile_type)

    return fallback_profile("HEB")

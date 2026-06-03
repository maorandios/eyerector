"""Tests for steel_catalog.json resolution."""

from __future__ import annotations

import pytest

from analyzer_service.steel_catalog import (
    catalog_profile_keys,
    fallback_profile,
    normalize_profile_name,
    resolve_from_text,
    resolve_from_text_for_role,
    resolve_profile_key,
)


def test_resolve_heb200() -> None:
    prof = resolve_profile_key("HEB200")
    assert prof.profile_key == "HEB200"
    assert prof.profile_type == "HEB"
    assert prof.dimensions[0] == 200.0


def test_resolve_rhs_key() -> None:
    prof = resolve_profile_key("200x200x10")
    assert prof.profile_type == "RHS"
    assert prof.dimensions == [200.0, 200.0, 10.0]


def test_alias_hebrew() -> None:
    key = resolve_from_text("עמוד חתו חב 200 גובה 4 מטר")
    assert key == "HEB200"


def test_role_aware_beam_vs_column() -> None:
    text = "Beam IPE500 spanning 8000 on 3 columns HEB300 height 4000"
    assert resolve_from_text_for_role(text, "column") == "HEB300"
    assert resolve_from_text_for_role(text, "beam") == "IPE500"


def test_fallback_profile() -> None:
    prof = fallback_profile("IPE")
    assert prof.profile_key == "IPE200"


def test_catalog_keys_non_empty() -> None:
    assert "HEB200" in catalog_profile_keys()
    assert "200x200x10" in catalog_profile_keys()


def test_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        resolve_profile_key("HEB9999")


def test_resolve_upn_channel() -> None:
    prof = resolve_profile_key("UPN200")
    assert prof.profile_type == "UPN"
    assert prof.shape == "U"
    # [depth, flange_width, web, flange]
    assert prof.dimensions == [200.0, 75.0, 8.5, 11.5]


def test_resolve_hem_and_upe() -> None:
    assert resolve_profile_key("HEM300").dimensions[0] == 340.0
    assert resolve_profile_key("UPE240").profile_type == "UPE"


def test_resolve_equal_angle() -> None:
    prof = resolve_profile_key("L100x100x10")
    assert prof.profile_type == "L"
    assert prof.shape == "L"
    assert prof.dimensions == [100.0, 100.0, 10.0]


def test_resolve_unequal_angle() -> None:
    prof = resolve_profile_key("L150x90x10")
    assert prof.dimensions == [150.0, 90.0, 10.0]


def test_resolve_chs() -> None:
    prof = resolve_profile_key("CHS168.3x5")
    assert prof.profile_type == "CHS"
    assert prof.shape == "CHS"
    assert prof.dimensions == [168.3, 5.0]


def test_resolve_shs_shorthand() -> None:
    prof = resolve_profile_key("SHS120x6")
    assert prof.profile_type == "RHS"
    assert prof.dimensions == [120.0, 120.0, 6.0]


def test_resolve_rhs_rectangular() -> None:
    prof = resolve_profile_key("200x100x8")
    assert prof.dimensions == [200.0, 100.0, 8.0]


def test_resolve_rhs_vision_compact_uppercase() -> None:
    """Claude/vision often emits RHS100X100X5 without lowercase separators."""
    prof = resolve_profile_key("RHS100X100X5")
    assert prof.profile_type == "RHS"
    assert prof.profile_key == "100x100x5"
    assert prof.dimensions == [100.0, 100.0, 5.0]
    assert normalize_profile_name("RHS100X100X5") == "100x100x5"


def test_resolve_arbitrary_chs_not_in_catalog() -> None:
    # On-the-fly resolution for sizes not pre-tabulated.
    prof = resolve_profile_key("CHS150x6")
    assert prof.profile_type == "CHS"
    assert prof.dimensions == [150.0, 6.0]


def test_text_resolution_for_new_families() -> None:
    assert resolve_from_text("a UPN240 channel") == "UPN240"
    assert resolve_from_text("angle L80x80x8 bracket") == "L80x80x8"
    assert resolve_from_text("pipe CHS219.1x6 brace") == "CHS219.1x6"


def test_role_aware_with_channels_and_angles() -> None:
    text = "beam UPN300 spanning on columns L100x100x10"
    assert resolve_from_text_for_role(text, "beam") == "UPN300"
    assert resolve_from_text_for_role(text, "column") == "L100x100x10"

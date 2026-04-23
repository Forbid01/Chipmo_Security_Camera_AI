"""Tests for T2-01 — Mongolian phone normalizer."""

import pytest

from shoplift_detector.app.core.phone_format import (
    COUNTRY_CODE,
    InvalidMongolianPhone,
    is_valid_phone,
    normalize_phone,
)


@pytest.mark.parametrize("raw,expected", [
    ("+97688123456", "+97688123456"),
    ("+976 8812-3456", "+97688123456"),
    ("+976-88-12-34-56", "+97688123456"),
    ("97688123456", "+97688123456"),
    ("88123456", "+97688123456"),       # local shorthand
    ("  +976 9912 3456  ", "+97699123456"),
    ("76123456", "+97676123456"),
])
def test_normalize_accepts_canonical_formats(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    "+976",
    "+9761234",                      # too short
    "+97612345678",                  # starts with 1 (not mobile)
    "12345678",                      # local but starts with 1
    "+97688123456789",               # too long
    "not-a-phone",
])
def test_normalize_rejects_bad_input(raw):
    with pytest.raises(InvalidMongolianPhone):
        normalize_phone(raw)


def test_normalize_rejects_none():
    with pytest.raises(InvalidMongolianPhone):
        normalize_phone(None)  # type: ignore[arg-type]


def test_is_valid_is_predicate_form():
    assert is_valid_phone("+97688123456") is True
    assert is_valid_phone("bad") is False


def test_country_code_constant_is_976():
    assert COUNTRY_CODE == "+976"

"""Mongolian phone-number validator + normalizer (T2-01).

Landing page accepts any of:

    +976 8812-3456
    +976-88-123456
    +97688123456
    88123456           (local — we prepend the country code)

All normalize to the E.164-ish form `+97688123456`. Leading digit of
the subscriber number is constrained to 6-9, which covers the current
MNT mobile + landline prefix range.
"""

from __future__ import annotations

import re

COUNTRY_CODE = "+976"

# Subscriber number: 8 digits, must start 6/7/8/9. Leading digit 0-5
# is either a historical fixed-line range we don't serve or invalid.
_SUBSCRIBER = re.compile(r"^[6789]\d{7}$")

# Acceptable punctuation between digits: spaces, dashes, or nothing.
_PUNCT = re.compile(r"[\s\-]")


class InvalidMongolianPhone(ValueError):
    """Raised when the caller-supplied phone number can't be normalized."""


def normalize_phone(raw: str) -> str:
    """Return the canonical `+97688123456` form, or raise.

    Accepts local (no country code) and international formats, strips
    spaces and dashes. Rejects numbers outside the Mongolian mobile/
    landline 8-digit range.
    """
    if raw is None:
        raise InvalidMongolianPhone("phone is required")
    stripped = _PUNCT.sub("", raw.strip())
    if not stripped:
        raise InvalidMongolianPhone("phone is required")

    # Accept "+976..." or "976..." as the international form; bare
    # 8-digit is treated as local and gets the country code prepended.
    if stripped.startswith("+976"):
        subscriber = stripped[4:]
    elif stripped.startswith("976") and len(stripped) > 8:
        subscriber = stripped[3:]
    else:
        subscriber = stripped

    if not _SUBSCRIBER.fullmatch(subscriber):
        raise InvalidMongolianPhone(
            f"phone must be a Mongolian 8-digit number (got {raw!r})"
        )

    return f"{COUNTRY_CODE}{subscriber}"


def is_valid_phone(raw: str) -> bool:
    """Predicate form — convenient for Pydantic validators."""
    try:
        normalize_phone(raw)
    except InvalidMongolianPhone:
        return False
    return True

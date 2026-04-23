"""Keyset pagination helpers.

Per docs/07-API-SPEC.md §8. Cursors are base64url-encoded JSON
payloads so they can ride in a querystring without escaping. Each
cursor encodes the ordering keys of the last row returned — for
time-series endpoints that's `(ts, id)`; the tuple is authoritative
because timestamps can collide across rows.

Usage in an endpoint:

    from app.core.pagination import (
        PaginationQuery,
        build_keyset_page,
        encode_cursor,
    )

    @router.get("/alerts")
    async def list_alerts(page: PaginationQuery = Depends()):
        cursor = page.decode()     # {"ts": "...", "id": 123} | None
        rows = await repo.fetch(limit=page.limit + 1, after=cursor)
        return build_keyset_page(rows, limit=page.limit, key=("event_time", "id"))
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, field_validator

MAX_LIMIT: int = 200
DEFAULT_LIMIT: int = 50

T = TypeVar("T")


class InvalidCursorError(ValueError):
    """Raised when a client supplies a malformed or tampered cursor.

    Handlers should convert this to a 400 response; keeping the
    cursor decoder strict prevents weird downstream errors.
    """


def encode_cursor(payload: dict[str, Any]) -> str:
    """Serialize `payload` to a URL-safe base64 string.

    Values are JSON-encoded; `datetime` is emitted as ISO-8601 UTC.
    The result is compact and unambiguous.
    """

    def _default(value):
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Cursor value of type {type(value).__name__} not JSON-serializable")

    raw = json.dumps(payload, separators=(",", ":"), default=_default).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    return encoded.decode("ascii")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    """Reverse of `encode_cursor`. Returns None for an empty input.

    Raises `InvalidCursorError` for malformed or non-object payloads so
    callers can return a clean 400 without exposing the underlying
    ValueError chain.
    """
    if cursor is None or cursor == "":
        return None
    # Re-pad for base64's 4-byte alignment requirement.
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError("cursor is not valid base64url") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidCursorError("cursor payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidCursorError("cursor payload must be a JSON object")
    return payload


class PaginationQuery(BaseModel):
    """Query-string shape shared by every paginated endpoint.

    Use as a FastAPI dependency: `page: PaginationQuery = Depends()`.
    """

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None)

    @field_validator("cursor")
    @classmethod
    def _validate_cursor(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        # Fast-fail malformed cursors at parse time so the handler
        # never has to re-decode later.
        decode_cursor(value)
        return value

    def decode(self) -> dict[str, Any] | None:
        return decode_cursor(self.cursor)


SortDir = Literal["asc", "desc"]


class KeysetPage(BaseModel, Generic[T]):
    """Standardized page response. Matches docs/07-API-SPEC.md §8."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def build_keyset_page(
    rows: list[dict[str, Any]],
    *,
    limit: int,
    key: tuple[str, ...] = ("event_time", "id"),
    items_field: str = "items",
) -> dict[str, Any]:
    """Turn a repo result into a keyset-paginated envelope.

    The convention is to fetch `limit + 1` rows in the repo. If the
    returned list has more than `limit` items we know there's another
    page and emit a `next_cursor` built from the last returned row's
    key tuple. The extra "probe" row is trimmed off before returning.

    `items_field` is the envelope key for the data array; defaults to
    `"items"` but callers can pass `"alerts"` etc. to keep existing
    response shapes intact.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")

    items = list(rows)
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        missing = [k for k in key if k not in last]
        if missing:
            raise KeyError(
                f"Row missing cursor key(s) {missing}; row keys: {list(last.keys())}"
            )
        next_cursor = encode_cursor({k: last[k] for k in key})

    return {
        items_field: items,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }

"""Tests for T02-19 — keyset pagination helper.

Covers:
- cursor roundtrip, including datetime serialization
- malformed / tampered / non-object cursors raise InvalidCursorError
- PaginationQuery validates at construction time
- build_keyset_page respects the fetch(limit+1) convention and omits
  next_cursor on the last page
- custom items_field keeps existing response shapes (alerts / cases)
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shoplift_detector.app.core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    InvalidCursorError,
    KeysetPage,
    PaginationQuery,
    build_keyset_page,
    decode_cursor,
    encode_cursor,
)

# ---------------------------------------------------------------------------
# Cursor encoding
# ---------------------------------------------------------------------------

def test_encode_decode_roundtrip_preserves_payload():
    payload = {"ts": "2026-04-21T10:00:00+00:00", "id": 1234}
    token = encode_cursor(payload)
    assert decode_cursor(token) == payload


def test_encode_datetime_emits_isoformat():
    ts = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)
    token = encode_cursor({"ts": ts, "id": 1})
    decoded = decode_cursor(token)
    assert decoded == {"ts": "2026-04-21T10:00:00+00:00", "id": 1}


def test_encode_rejects_unserializable_value():
    with pytest.raises(TypeError):
        encode_cursor({"ts": object()})


def test_decode_none_and_empty_string_return_none():
    assert decode_cursor(None) is None
    assert decode_cursor("") is None


@pytest.mark.parametrize("bad_value", [
    "!!!",                          # invalid base64
    "eyJ0cyI6Im5vdC1qc29uIn0aa",    # base64 of malformed json segment
])
def test_decode_raises_for_malformed_input(bad_value):
    with pytest.raises(InvalidCursorError):
        decode_cursor(bad_value)


def test_decode_rejects_non_object_payloads():
    # base64 of JSON `[]`
    import base64
    token = base64.urlsafe_b64encode(b"[]").rstrip(b"=").decode("ascii")
    with pytest.raises(InvalidCursorError, match="JSON object"):
        decode_cursor(token)


def test_decode_handles_unpadded_base64():
    # base64 without padding — the decoder must re-pad internally.
    import base64
    raw = b'{"id":1}'
    token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    assert decode_cursor(token) == {"id": 1}


# ---------------------------------------------------------------------------
# PaginationQuery
# ---------------------------------------------------------------------------

def test_pagination_query_defaults():
    q = PaginationQuery()
    assert q.limit == DEFAULT_LIMIT
    assert q.cursor is None


def test_pagination_query_rejects_oversize_limit():
    with pytest.raises(ValidationError):
        PaginationQuery(limit=MAX_LIMIT + 1)


def test_pagination_query_rejects_zero_limit():
    with pytest.raises(ValidationError):
        PaginationQuery(limit=0)


def test_pagination_query_rejects_malformed_cursor_at_parse_time():
    with pytest.raises(ValidationError):
        PaginationQuery(cursor="!!!")


def test_pagination_query_decodes_valid_cursor():
    token = encode_cursor({"ts": "2026-01-01T00:00:00+00:00", "id": 7})
    q = PaginationQuery(cursor=token)
    assert q.decode() == {"ts": "2026-01-01T00:00:00+00:00", "id": 7}


# ---------------------------------------------------------------------------
# build_keyset_page
# ---------------------------------------------------------------------------

def _make_row(i: int):
    return {
        "id": i,
        "event_time": datetime(2026, 4, 21, 10, 0, i, tzinfo=UTC),
        "description": f"alert {i}",
    }


def test_build_page_emits_next_cursor_when_probe_row_present():
    rows = [_make_row(i) for i in range(11)]  # fetched limit+1
    page = build_keyset_page(rows, limit=10)
    assert len(page["items"]) == 10
    assert page["has_more"] is True
    assert page["next_cursor"] is not None

    cursor_payload = decode_cursor(page["next_cursor"])
    # next_cursor encodes the LAST row returned, not the probe row
    assert cursor_payload["id"] == 9


def test_build_page_on_last_page_returns_none_cursor():
    rows = [_make_row(i) for i in range(3)]
    page = build_keyset_page(rows, limit=10)
    assert page["items"] == rows
    assert page["has_more"] is False
    assert page["next_cursor"] is None


def test_build_page_empty_input():
    page = build_keyset_page([], limit=20)
    assert page["items"] == []
    assert page["has_more"] is False
    assert page["next_cursor"] is None


def test_build_page_respects_custom_items_field():
    rows = [_make_row(i) for i in range(5)]
    page = build_keyset_page(rows, limit=10, items_field="alerts")
    assert "alerts" in page
    assert "items" not in page
    assert page["alerts"] == rows


def test_build_page_raises_when_cursor_key_missing_from_row():
    rows = [{"id": 1, "description": "no event_time here"}]
    with pytest.raises(KeyError, match="event_time"):
        build_keyset_page(
            rows + [{"id": 2, "description": "second"}],
            limit=1,
        )


def test_build_page_rejects_non_positive_limit():
    with pytest.raises(ValueError, match="limit"):
        build_keyset_page([_make_row(1)], limit=0)


def test_build_page_accepts_custom_key_tuple():
    # For tables keyed by (store_id, day) — the materialized view
    # from T02-16 — the caller supplies a different key.
    rows = [
        {"store_id": 1, "day": datetime(2026, 4, 21, tzinfo=UTC), "count": 3},
        {"store_id": 1, "day": datetime(2026, 4, 20, tzinfo=UTC), "count": 7},
        {"store_id": 1, "day": datetime(2026, 4, 19, tzinfo=UTC), "count": 2},
    ]
    page = build_keyset_page(rows, limit=2, key=("store_id", "day"))
    assert page["has_more"] is True
    cursor_payload = decode_cursor(page["next_cursor"])
    assert cursor_payload["store_id"] == 1
    assert "day" in cursor_payload


# ---------------------------------------------------------------------------
# KeysetPage schema shape
# ---------------------------------------------------------------------------

def test_keyset_page_response_shape_matches_api_spec():
    page: KeysetPage[dict] = KeysetPage(
        items=[{"id": 1}, {"id": 2}],
        next_cursor="abc",
        has_more=True,
    )
    dumped = page.model_dump()
    assert set(dumped.keys()) == {"items", "next_cursor", "has_more"}

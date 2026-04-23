"""Tests for AuditLogRepository.

Locks in the polymorphic-resource contract required by schema lock §7.5
and the insert/list/retention surface. Uses a mocked async session so
the SQL shape and validation rules are enforced without a live DB.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from shoplift_detector.app.db.models.audit_log import AUDIT_ACTIONS
from shoplift_detector.app.db.repository.audit_log import AuditLogRepository


class _FakeResult:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or ([row] if row else [])
        self.rowcount = rowcount

    def mappings(self):
        return _FakeResult(row=self._row, rows=self._rows, rowcount=self.rowcount)

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


# ---------------------------------------------------------------------------
# Action constants
# ---------------------------------------------------------------------------

def test_audit_actions_cover_docs_canonical_set():
    expected = {
        "view_clip", "download_clip", "share_clip",
        "label_clip", "delete_clip",
        "view_alert", "export_alerts",
        "config_change", "user_created", "user_deleted",
    }
    assert expected.issubset(set(AUDIT_ACTIONS.keys()))


# ---------------------------------------------------------------------------
# log(): validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_rejects_empty_action():
    db = AsyncMock()
    repo = AuditLogRepository(db)
    with pytest.raises(ValueError, match="action is required"):
        await repo.log(action="")
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_log_rejects_multiple_resource_ids_at_once():
    db = AsyncMock()
    repo = AuditLogRepository(db)
    with pytest.raises(ValueError, match="at most one"):
        await repo.log(
            action="view_clip",
            resource_type="clip",
            resource_int_id=1,
            resource_uuid=uuid4(),
        )
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_log_rejects_resource_id_without_resource_type():
    db = AsyncMock()
    repo = AuditLogRepository(db)
    with pytest.raises(ValueError, match="resource_type is required"):
        await repo.log(action="view_clip", resource_int_id=1)
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# log(): happy path shapes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_inserts_with_integer_resource_and_serialized_details():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeResult(row=(42,))

    db = AsyncMock()
    db.execute = execute

    repo = AuditLogRepository(db)
    new_id = await repo.log(
        action=AUDIT_ACTIONS["view_alert"],
        user_id=7,
        resource_type="alert",
        resource_int_id=1234,
        details={"reason": "review"},
        ip_address="203.0.113.5",
        user_agent="Mozilla/5.0",
    )

    assert new_id == 42
    assert "INSERT INTO audit_log" in captured["query"]
    assert captured["params"]["action"] == "view_alert"
    assert captured["params"]["resource_type"] == "alert"
    assert captured["params"]["resource_int_id"] == 1234
    assert captured["params"]["resource_uuid"] is None
    assert captured["params"]["resource_key"] is None
    # details must be JSON-encoded for the JSONB cast
    assert json.loads(captured["params"]["details"]) == {"reason": "review"}
    # server-side default should be used when caller omits timestamp
    assert "now()" in captured["query"]
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_log_accepts_uuid_resource_and_stringifies_it():
    case_id = uuid4()
    captured: dict = {}

    async def execute(query, params=None):
        captured["params"] = params
        return _FakeResult(row=(1,))

    db = AsyncMock()
    db.execute = execute
    repo = AuditLogRepository(db)

    await repo.log(
        action=AUDIT_ACTIONS["label_clip"],
        user_id=9,
        resource_type="case",
        resource_uuid=case_id,
        details={"label": "theft"},
    )

    assert captured["params"]["resource_uuid"] == str(case_id)
    assert captured["params"]["resource_int_id"] is None


@pytest.mark.asyncio
async def test_log_accepts_opaque_resource_key_for_non_db_resources():
    captured: dict = {}

    async def execute(query, params=None):
        captured["params"] = params
        return _FakeResult(row=(1,))

    db = AsyncMock()
    db.execute = execute
    repo = AuditLogRepository(db)

    await repo.log(
        action=AUDIT_ACTIONS["config_change"],
        user_id=1,
        resource_type="settings_key",
        resource_key="ai.rag_check_enabled",
        details={"from": True, "to": False},
    )

    assert captured["params"]["resource_key"] == "ai.rag_check_enabled"
    assert captured["params"]["resource_int_id"] is None
    assert captured["params"]["resource_uuid"] is None


@pytest.mark.asyncio
async def test_log_uses_explicit_timestamp_when_provided():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeResult(row=(1,))

    db = AsyncMock()
    db.execute = execute
    repo = AuditLogRepository(db)

    fixed_ts = datetime(2026, 4, 21, 15, 30, tzinfo=UTC)
    await repo.log(
        action="view_clip",
        user_id=3,
        timestamp=fixed_ts,
    )

    assert ":timestamp" in captured["query"]
    assert captured["params"]["timestamp"] == fixed_ts


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_for_resource_filters_by_type_and_int_id():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeResult(rows=[{"id": 1, "action": "view_alert"}])

    db = AsyncMock()
    db.execute = execute
    repo = AuditLogRepository(db)

    rows = await repo.list_for_resource(
        "alert", resource_int_id=42, limit=20
    )

    assert len(rows) == 1
    assert "resource_type = :resource_type" in captured["query"]
    assert "resource_int_id = :resource_int_id" in captured["query"]
    assert captured["params"]["resource_int_id"] == 42


@pytest.mark.asyncio
async def test_list_by_action_applies_since_filter_when_provided():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeResult(rows=[])

    db = AsyncMock()
    db.execute = execute
    repo = AuditLogRepository(db)

    since = datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
    await repo.list_by_action("delete_clip", since=since, limit=50)

    assert "timestamp >= :since" in captured["query"]
    assert captured["params"]["since"] == since


@pytest.mark.asyncio
async def test_delete_older_than_days_computes_cutoff():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeResult(rowcount=17)

    db = AsyncMock()
    db.execute = execute
    repo = AuditLogRepository(db)

    removed = await repo.delete_older_than_days(365)

    assert removed == 17
    assert "DELETE FROM audit_log" in captured["query"]
    cutoff = captured["params"]["cutoff"]
    assert cutoff.tzinfo is UTC
    assert datetime.now(UTC) - cutoff >= timedelta(days=364, hours=23)

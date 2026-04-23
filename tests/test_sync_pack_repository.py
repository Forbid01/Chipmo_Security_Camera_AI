"""Tests for SyncPackRepository.

Exercises the version/status/signature lifecycle. Uses a mocked async
session so we lock in SQL param shape and state-transition guards
without needing a live Postgres.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from shoplift_detector.app.db.models.sync_pack import SYNC_PACK_STATUSES
from shoplift_detector.app.db.repository.sync_packs import SyncPackRepository


class _FakeMappingResult:
    def __init__(self, row=None, rows=None, rowcount=1):
        self._row = row
        self._rows = rows or ([row] if row else [])
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


def test_sync_pack_statuses_enum_matches_migration_constraint():
    assert set(SYNC_PACK_STATUSES) == {
        "pending", "downloaded", "applied", "failed", "rolled_back",
    }


@pytest.mark.asyncio
async def test_create_inserts_with_pending_status_and_records_signature():
    new_id = uuid4()
    now = datetime.now(UTC)
    returned_row = {
        "id": new_id,
        "store_id": 5,
        "version": "v1.2.0",
        "weights_hash": "sha256:abc",
        "qdrant_snapshot_id": "snap-xyz",
        "case_count": 42,
        "s3_path": "s3://chipmo/sync_packs/5/v1.2.0.tar.gz",
        "signature": "hmac-sha256:deadbeef",
        "status": "pending",
        "applied_at": None,
        "created_at": now,
        "updated_at": now,
    }

    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult(row=returned_row)

    db = AsyncMock()
    db.execute = execute

    repo = SyncPackRepository(db)
    result = await repo.create(
        store_id=5,
        version="v1.2.0",
        weights_hash="sha256:abc",
        qdrant_snapshot_id="snap-xyz",
        case_count=42,
        s3_path="s3://chipmo/sync_packs/5/v1.2.0.tar.gz",
        signature="hmac-sha256:deadbeef",
    )

    assert result["id"] == new_id
    assert result["status"] == "pending"
    assert result["signature"] == "hmac-sha256:deadbeef"
    assert "INSERT INTO sync_packs" in captured["query"]
    assert captured["params"]["version"] == "v1.2.0"
    assert captured["params"]["signature"] == "hmac-sha256:deadbeef"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_status_rejects_unknown_status():
    db = AsyncMock()
    repo = SyncPackRepository(db)

    with pytest.raises(ValueError, match="Invalid sync_pack status"):
        await repo.update_status(uuid4(), "synced-maybe")

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_status_accepts_every_valid_value():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeMappingResult(rowcount=1))
    repo = SyncPackRepository(db)

    for status in SYNC_PACK_STATUSES:
        assert await repo.update_status(uuid4(), status) is True


@pytest.mark.asyncio
async def test_mark_downloaded_only_transitions_from_pending():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult(rowcount=1)

    db = AsyncMock()
    db.execute = execute
    repo = SyncPackRepository(db)

    pack_id = uuid4()
    ok = await repo.mark_downloaded(pack_id)

    assert ok is True
    assert "status = 'downloaded'" in captured["query"]
    assert "status = 'pending'" in captured["query"]  # WHERE guard
    assert captured["params"]["id"] == str(pack_id)


@pytest.mark.asyncio
async def test_mark_applied_sets_timestamp():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult(rowcount=1)

    db = AsyncMock()
    db.execute = execute
    repo = SyncPackRepository(db)

    pack_id = uuid4()
    fixed_now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)

    ok = await repo.mark_applied(pack_id, now=fixed_now)

    assert ok is True
    assert "status = 'applied'" in captured["query"]
    assert "applied_at = :now" in captured["query"]
    assert "status IN ('pending', 'downloaded')" in captured["query"]
    assert captured["params"]["now"] == fixed_now


@pytest.mark.asyncio
async def test_mark_failed_guards_against_overwriting_terminal_states():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        return _FakeMappingResult(rowcount=1)

    db = AsyncMock()
    db.execute = execute
    repo = SyncPackRepository(db)

    assert await repo.mark_failed(uuid4()) is True
    assert "status = :status" in captured["query"]
    assert "status NOT IN ('applied', 'failed', 'rolled_back')" in captured["query"]


@pytest.mark.asyncio
async def test_get_latest_applied_for_store_filters_by_applied_status():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult(row={
            "id": uuid4(),
            "store_id": 7,
            "status": "applied",
            "version": "v1.1.0",
        })

    db = AsyncMock()
    db.execute = execute
    repo = SyncPackRepository(db)

    row = await repo.get_latest_applied_for_store(7)

    assert row["status"] == "applied"
    assert "status = 'applied'" in captured["query"]
    assert captured["params"] == {"store_id": 7}


@pytest.mark.asyncio
async def test_list_for_store_orders_by_created_at_desc():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        return _FakeMappingResult(rows=[
            {"id": uuid4(), "store_id": 1, "version": "v1.2.0"},
            {"id": uuid4(), "store_id": 1, "version": "v1.1.0"},
        ])

    db = AsyncMock()
    db.execute = execute
    repo = SyncPackRepository(db)

    rows = await repo.list_for_store(1, limit=20)

    assert len(rows) == 2
    assert "ORDER BY created_at DESC" in captured["query"]

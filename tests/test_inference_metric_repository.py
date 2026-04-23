"""Tests for InferenceMetricRepository.

Locks in the SQL shape for upsert, batch, aggregation and retention
against a mocked async session. No live Postgres required.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from shoplift_detector.app.db.repository.inference_metrics import (
    InferenceMetricRepository,
)


class _FakeMappingResult:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or ([row] if row else [])
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


@pytest.mark.asyncio
async def test_record_upserts_with_on_conflict_clause():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult()

    db = AsyncMock()
    db.execute = execute
    repo = InferenceMetricRepository(db)

    ts = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)

    await repo.record(
        camera_id=7,
        timestamp=ts,
        fps=14.5,
        yolo_latency_ms=12.0,
        reid_latency_ms=8.0,
        rag_latency_ms=42.0,
        vlm_latency_ms=520.0,
        end_to_end_latency_ms=600.0,
    )

    assert "INSERT INTO inference_metrics" in captured["query"]
    assert "ON CONFLICT (camera_id, timestamp) DO UPDATE" in captured["query"]
    assert captured["params"]["camera_id"] == 7
    assert captured["params"]["timestamp"] == ts
    assert captured["params"]["fps"] == 14.5
    assert captured["params"]["end_to_end_latency_ms"] == 600.0
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_record_naive_timestamp_is_coerced_to_utc():
    captured: dict = {}

    async def execute(query, params=None):
        captured["params"] = params
        return _FakeMappingResult()

    db = AsyncMock()
    db.execute = execute
    repo = InferenceMetricRepository(db)

    naive = datetime(2026, 4, 21, 12, 0)  # no tzinfo
    await repo.record(camera_id=1, timestamp=naive, fps=10.0)

    ts = captured["params"]["timestamp"]
    assert ts.tzinfo is UTC
    assert ts.year == 2026 and ts.hour == 12


@pytest.mark.asyncio
async def test_record_batch_applies_each_sample_and_commits_once():
    calls: list[dict] = []

    async def execute(query, params=None):
        calls.append(params)
        return _FakeMappingResult()

    db = AsyncMock()
    db.execute = execute
    repo = InferenceMetricRepository(db)

    now = datetime.now(UTC)
    samples = [
        {"camera_id": 1, "timestamp": now, "fps": 12.0},
        {"camera_id": 2, "timestamp": now, "fps": 15.0, "yolo_latency_ms": 10.0},
    ]

    count = await repo.record_batch(samples)

    assert count == 2
    assert [c["camera_id"] for c in calls] == [1, 2]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_batch_noop_for_empty_list_does_not_commit():
    db = AsyncMock()
    repo = InferenceMetricRepository(db)

    count = await repo.record_batch([])

    assert count == 0
    db.execute.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_recent_for_camera_orders_desc_with_limit():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult(rows=[
            {"camera_id": 1, "timestamp": datetime.now(UTC), "fps": 14.0},
        ])

    db = AsyncMock()
    db.execute = execute
    repo = InferenceMetricRepository(db)

    rows = await repo.get_recent_for_camera(1, limit=10)

    assert len(rows) == 1
    assert "ORDER BY timestamp DESC" in captured["query"]
    assert captured["params"] == {"camera_id": 1, "limit": 10}


@pytest.mark.asyncio
async def test_aggregate_for_store_joins_cameras_and_uses_p95():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult(row={
            "avg_fps": 14.0,
            "avg_e2e_ms": 580.0,
            "p95_e2e_ms": 900.0,
            "avg_yolo_ms": 12.0,
            "avg_rag_ms": 40.0,
            "avg_vlm_ms": 500.0,
            "sample_count": 128,
        })

    db = AsyncMock()
    db.execute = execute
    repo = InferenceMetricRepository(db)

    since = datetime(2026, 4, 21, 0, 0, tzinfo=UTC)
    until = datetime(2026, 4, 21, 23, 59, tzinfo=UTC)

    result = await repo.aggregate_for_store(3, since=since, until=until)

    assert result["p95_e2e_ms"] == 900.0
    assert result["sample_count"] == 128
    assert "JOIN cameras c ON c.id = im.camera_id" in captured["query"]
    assert "PERCENTILE_CONT(0.95)" in captured["query"]
    assert captured["params"]["store_id"] == 3


@pytest.mark.asyncio
async def test_delete_older_than_days_computes_cutoff_and_issues_delete():
    captured: dict = {}

    async def execute(query, params=None):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeMappingResult(rowcount=42)

    db = AsyncMock()
    db.execute = execute
    repo = InferenceMetricRepository(db)

    removed = await repo.delete_older_than_days(30)

    assert removed == 42
    assert "DELETE FROM inference_metrics" in captured["query"]
    cutoff = captured["params"]["cutoff"]
    assert cutoff.tzinfo is UTC
    assert datetime.now(UTC) - cutoff >= timedelta(days=29, hours=23)

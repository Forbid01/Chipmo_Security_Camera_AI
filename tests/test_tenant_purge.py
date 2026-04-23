"""Tests for T1-11 — 90-day grace + data purge cron."""

import importlib.util
import pathlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from shoplift_detector.app.services.tenant_purge import (
    PURGE_AFTER,
    TENANT_PURGE_ACTION,
    PurgeReport,
    _TENANT_TABLES,
    find_purge_candidates,
    purge_tenant,
    run_purge_cron,
)

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260422_06_add_status_changed_at.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "status_changed_at_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------

def test_migration_revision_chain():
    module = _load_migration()
    assert module.revision == "20260422_06"
    assert module.down_revision == "20260422_05"


def test_migration_adds_status_changed_at_with_default():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ" in text
    # Default keeps existing rows populated so the cron doesn't skip
    # every tenant on first deploy.
    assert "DEFAULT now()" in text


def test_migration_creates_churned_purge_index():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE INDEX IF NOT EXISTS idx_tenants_churned_purge" in text
    assert "WHERE status = 'churned'" in text


def test_downgrade_drops_column_and_index():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    body = text.split("def downgrade()", 1)[1]
    assert "DROP INDEX IF EXISTS idx_tenants_churned_purge" in body
    assert "DROP COLUMN IF EXISTS status_changed_at" in body


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_purge_window_is_90_days():
    assert PURGE_AFTER == timedelta(days=90)


def test_tenant_tables_cover_the_expected_scope():
    # Must be identical (as a set) to the T1-03 list so a mismatch
    # is caught early. Ordering is intentionally different — purge
    # deletes leaves first to respect FK direction.
    from tests.test_tenant_id_columns_migration import TENANT_SCOPED_TABLES
    assert set(_TENANT_TABLES) == set(TENANT_SCOPED_TABLES)


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows=None, rowcount=0):
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, candidate_rows=None):
        self._candidate_rows = candidate_rows or []
        self.executed: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, query, params=None):
        q = str(query)
        self.executed.append((q, params))
        if "SELECT tenant_id" in q and "FROM tenants" in q and "churned" in q:
            return _FakeResult(rows=self._candidate_rows)
        if q.strip().startswith("DELETE FROM"):
            return _FakeResult(rowcount=3)
        if "INSERT INTO audit_log" in q:
            return _FakeResult(rows=[(1,)])
        return _FakeResult()

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_find_purge_candidates_uses_90d_cutoff():
    now = datetime(2026, 4, 22, tzinfo=UTC)
    db = _FakeDB(candidate_rows=[])
    await find_purge_candidates(db, now=now)
    q, params = db.executed[-1]
    assert "status = 'churned'" in q
    assert "status_changed_at IS NOT NULL" in q
    assert params["cutoff"] == now - PURGE_AFTER


# ---------------------------------------------------------------------------
# Purge pipeline
# ---------------------------------------------------------------------------

class _FakeQdrant:
    def __init__(self, raise_on=None):
        self.dropped: list[str] = []
        self._raise_on = raise_on

    async def delete_collection(self, name: str) -> None:
        if self._raise_on == "qdrant":
            raise RuntimeError("qdrant boom")
        self.dropped.append(name)


class _FakeObjectStore:
    def __init__(self, count=42, raise_on=None):
        self.deleted_prefixes: list[str] = []
        self._count = count
        self._raise_on = raise_on

    async def delete_prefix(self, prefix: str) -> int:
        if self._raise_on == "minio":
            raise RuntimeError("minio boom")
        self.deleted_prefixes.append(prefix)
        return self._count


@pytest.mark.asyncio
async def test_purge_deletes_qdrant_minio_and_sql():
    tid = uuid4()
    db = _FakeDB()
    qd = _FakeQdrant()
    obj = _FakeObjectStore(count=17)

    report = await purge_tenant(
        db, tenant_id=tid, qdrant=qd, object_store=obj
    )

    assert report.ok
    assert report.qdrant_dropped is True
    assert report.objects_deleted == 17
    # Every tenant-scoped table got a DELETE.
    assert set(report.rows_deleted.keys()) == set(_TENANT_TABLES)
    # Qdrant collection name canonicalized.
    assert qd.dropped == [f"reid_tenant_{str(tid).replace('-', '_')}"]
    # MinIO prefix scoped to tenant.
    assert obj.deleted_prefixes == [f"tenant_{tid}/"]
    # Audit row was written.
    actions = [p for q, p in db.executed if "audit_log" in q]
    assert actions, "expected an audit_log insert"
    assert actions[0]["action"] == TENANT_PURGE_ACTION
    assert db.committed is True


@pytest.mark.asyncio
async def test_purge_continues_on_external_failure_and_reports_error():
    tid = uuid4()
    db = _FakeDB()
    qd = _FakeQdrant(raise_on="qdrant")
    obj = _FakeObjectStore()

    report = await purge_tenant(
        db, tenant_id=tid, qdrant=qd, object_store=obj
    )

    # External failure logged but SQL + audit still happened — we
    # don't want a partial-purge state to linger on the tenant row.
    assert report.ok is False
    assert any("qdrant_delete_failed" in e for e in report.errors)
    assert report.objects_deleted > 0
    assert db.committed is True


@pytest.mark.asyncio
async def test_purge_without_external_clients_only_runs_sql():
    tid = uuid4()
    db = _FakeDB()

    report = await purge_tenant(db, tenant_id=tid)

    assert report.qdrant_dropped is False
    assert report.objects_deleted == 0
    assert report.rows_deleted  # SQL ran
    assert db.committed is True


# ---------------------------------------------------------------------------
# Cron loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_purge_cron_processes_each_candidate():
    tid1, tid2 = uuid4(), uuid4()
    now = datetime(2026, 4, 22, tzinfo=UTC)
    db = _FakeDB(
        candidate_rows=[
            {"tenant_id": tid1, "legal_name": "a", "status": "churned",
             "status_changed_at": now - timedelta(days=100)},
            {"tenant_id": tid2, "legal_name": "b", "status": "churned",
             "status_changed_at": now - timedelta(days=95)},
        ]
    )
    reports = await run_purge_cron(db, now=now)
    assert len(reports) == 2
    assert all(r.ok for r in reports)
    assert {r.tenant_id for r in reports} == {str(tid1), str(tid2)}


@pytest.mark.asyncio
async def test_run_purge_cron_with_no_candidates_is_noop():
    db = _FakeDB(candidate_rows=[])
    reports = await run_purge_cron(db)
    assert reports == []
    assert db.committed is False  # nothing to commit


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

def test_purge_report_ok_reflects_errors():
    r = PurgeReport(tenant_id="x")
    assert r.ok is True
    r.errors.append("boom")
    assert r.ok is False

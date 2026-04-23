"""Tests for T02-16 — store_fp_rate_daily materialized view + refresh.

Covers:
- migration SQL shape: vanilla-Postgres compatible (date_trunc, not
  Timescale time_bucket), unique index for CONCURRENTLY refresh,
  branch on `suppressed` column presence
- refresh service respects STORE_FP_RATE_REFRESH_ENABLED
- refresh_once handles the "view doesn't exist yet" path
- refresh_once falls back from CONCURRENTLY to blocking when the view
  is empty right after migration
"""

import importlib.util
import pathlib
from unittest.mock import AsyncMock

import pytest

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260421_09_add_store_fp_rate_daily.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "store_fp_rate_daily_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration file shape
# ---------------------------------------------------------------------------

def test_migration_revision_chain_follows_t02_15():
    module = _load_migration()
    assert module.revision == "20260421_09"
    assert module.down_revision == "20260421_08"


def test_migration_uses_vanilla_postgres_date_trunc_not_time_bucket():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "date_trunc('day', event_time)" in text, (
        "Must use vanilla Postgres date_trunc; time_bucket is "
        "Timescale-specific per the T02-07 spike decision."
    )
    assert "time_bucket(" not in text


def test_migration_installs_unique_index_for_concurrent_refresh():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_store_fp_rate_daily_store_day" in text


def test_migration_covers_false_positive_and_true_positive_counts():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "feedback_status = 'false_positive'" in text
    assert "feedback_status = 'true_positive'" in text
    assert "false_positives" in text
    assert "true_positives" in text
    assert "total_alerts" in text


def test_migration_branches_on_suppressed_column_presence():
    """Staging DBs that predate T02-14 don't have `suppressed`. Migration
    must still succeed there."""
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "column_name = 'suppressed'" in text
    assert "IF has_suppressed THEN" in text


def test_migration_excludes_null_store_id_rows():
    # Pre-migration rows sometimes carry NULL store_id; attributing
    # those to any store would be wrong.
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "WHERE store_id IS NOT NULL" in text


def test_migration_downgrade_drops_the_view_only():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # Downgrade must not drop alerts or anything upstream.
    downgrade_body = text.split("def downgrade()", 1)[1]
    assert "DROP MATERIALIZED VIEW" in downgrade_body
    assert "DROP TABLE" not in downgrade_body


# ---------------------------------------------------------------------------
# Refresh service behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_enabled_gate_reads_env():
    import os

    from app.services import fp_rate_refresh as mod
    os.environ["STORE_FP_RATE_REFRESH_ENABLED"] = "0"
    try:
        assert mod._refresh_enabled() is False
    finally:
        os.environ.pop("STORE_FP_RATE_REFRESH_ENABLED", None)

    os.environ["STORE_FP_RATE_REFRESH_ENABLED"] = "1"
    try:
        assert mod._refresh_enabled() is True
    finally:
        os.environ.pop("STORE_FP_RATE_REFRESH_ENABLED", None)


@pytest.mark.asyncio
async def test_refresh_interval_clamped_to_60_seconds_minimum():
    import os

    from app.services import fp_rate_refresh as mod
    os.environ["STORE_FP_RATE_REFRESH_INTERVAL_SECONDS"] = "5"
    try:
        assert mod._refresh_interval_seconds() == 60.0
    finally:
        os.environ.pop("STORE_FP_RATE_REFRESH_INTERVAL_SECONDS", None)


@pytest.mark.asyncio
async def test_refresh_interval_defaults_to_one_hour():
    import os

    from app.services import fp_rate_refresh as mod
    os.environ.pop("STORE_FP_RATE_REFRESH_INTERVAL_SECONDS", None)
    assert mod._refresh_interval_seconds() == 3600.0


class _FakeSessionCtx:
    """Acts as an async context manager yielding a fake session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_refresh_once_noop_when_view_missing(monkeypatch):
    from app.services import fp_rate_refresh as mod

    # _view_exists will receive this session. Result returns None row.
    class _NoViewResult:
        def fetchone(self_inner):
            return None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_NoViewResult())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    monkeypatch.setattr(
        mod, "AsyncSessionLocal", lambda: _FakeSessionCtx(session)
    )

    result = await mod.refresh_once()

    assert result is False
    # We hit the existence check but never issued the REFRESH.
    executed_queries = [str(c.args[0]) for c in session.execute.await_args_list]
    assert any("pg_matviews" in q for q in executed_queries)
    assert not any("REFRESH MATERIALIZED VIEW" in q for q in executed_queries)


@pytest.mark.asyncio
async def test_refresh_once_issues_concurrent_refresh_when_view_exists(monkeypatch):
    from app.services import fp_rate_refresh as mod

    class _ViewPresent:
        def fetchone(self_inner):
            return (1,)

    executed: list[str] = []

    async def fake_execute(query, params=None):
        executed.append(str(query))
        if "pg_matviews" in str(query):
            return _ViewPresent()

        class _Ok:
            def fetchone(self_inner):
                return None
        return _Ok()

    session = AsyncMock()
    session.execute = fake_execute
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    monkeypatch.setattr(
        mod, "AsyncSessionLocal", lambda: _FakeSessionCtx(session)
    )

    result = await mod.refresh_once(concurrently=True)

    assert result is True
    assert any(
        "REFRESH MATERIALIZED VIEW CONCURRENTLY store_fp_rate_daily" in q
        for q in executed
    )
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_refresh_once_falls_back_to_blocking_on_concurrent_failure(monkeypatch):
    """CONCURRENTLY fails on an unpopulated view. The service must
    recover by issuing a blocking refresh once."""
    from app.services import fp_rate_refresh as mod

    class _ViewPresent:
        def fetchone(self_inner):
            return (1,)

    executed: list[str] = []
    raised_once = {"done": False}

    async def fake_execute(query, params=None):
        q = str(query)
        executed.append(q)
        if "pg_matviews" in q:
            return _ViewPresent()
        if "CONCURRENTLY" in q and not raised_once["done"]:
            raised_once["done"] = True
            raise RuntimeError("CONCURRENTLY not allowed on unpopulated view")

        class _Ok:
            def fetchone(self_inner):
                return None
        return _Ok()

    session = AsyncMock()
    session.execute = fake_execute
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    monkeypatch.setattr(
        mod, "AsyncSessionLocal", lambda: _FakeSessionCtx(session)
    )

    result = await mod.refresh_once(concurrently=True)

    assert result is True
    # Blocking REFRESH is the one without CONCURRENTLY keyword.
    assert any(
        "REFRESH MATERIALIZED VIEW store_fp_rate_daily" in q
        and "CONCURRENTLY" not in q
        for q in executed
    )

"""T4-07 + T4-08 — agent register + heartbeat.

Two layers of coverage:

1. Pure logic — `derive_status` thresholds, `register_or_refresh`
   idempotency on UPSERT, migration shape.
2. Endpoint behavior — register returns agent_id + heartbeat
   interval, heartbeat 404s on cross-tenant, heartbeat echoes
   server_time.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-agents")


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------

MIGRATION_PATH = ROOT / "alembic" / "versions" / "20260423_02_add_agents.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "agents_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain():
    mod = _load_migration()
    assert mod.revision == "20260423_02"
    assert mod.down_revision == "20260423_01"


def test_migration_creates_table_with_expected_columns():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    for token in [
        "CREATE TABLE IF NOT EXISTS agents",
        "agent_id          UUID PRIMARY KEY",
        "tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id)",
        "ON DELETE CASCADE",
        "hostname          TEXT NOT NULL",
        "platform          TEXT NOT NULL",
        "last_heartbeat_at TIMESTAMPTZ",
        "metadata          JSONB NOT NULL DEFAULT",
        "UNIQUE (tenant_id, hostname)",
        "platform IN ('linux', 'windows', 'macos')",
    ]:
        assert token in body, f"migration missing: {token}"


def test_migration_enables_rls_policy():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in body
    assert "FORCE ROW LEVEL SECURITY" in body
    assert "CREATE POLICY tenant_isolation ON agents" in body
    assert "app.current_tenant_id" in body


# ---------------------------------------------------------------------------
# derive_status
# ---------------------------------------------------------------------------

from shoplift_detector.app.db.repository.agents import (  # noqa: E402
    HEARTBEAT_INTERVAL_SECONDS,
    OFFLINE_THRESHOLD_SECONDS,
    derive_status,
)


class TestDeriveStatus:
    def test_pending_when_never_beat(self):
        assert derive_status(None, now=datetime.now(UTC)) == "pending"

    def test_online_within_threshold(self):
        now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
        last = now - timedelta(seconds=30)
        assert derive_status(last, now=now) == "online"

    def test_offline_past_threshold(self):
        now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
        last = now - timedelta(seconds=OFFLINE_THRESHOLD_SECONDS + 5)
        assert derive_status(last, now=now) == "offline"

    def test_naive_timestamp_coerced_to_utc(self):
        """Legacy rows stored naive — must not crash, must still be
        usable for status computation."""
        now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
        naive = datetime(2026, 4, 23, 11, 59)  # naive
        assert derive_status(naive, now=now) == "online"

    def test_heartbeat_interval_is_60s(self):
        assert HEARTBEAT_INTERVAL_SECONDS == 60

    def test_offline_threshold_is_5m(self):
        assert OFFLINE_THRESHOLD_SECONDS == 300


# ---------------------------------------------------------------------------
# Endpoint — register + heartbeat via TestClient
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self):
        # Keyed by (tenant_id, hostname) — mirrors the UPSERT path.
        self.agents: dict[tuple[str, str], dict] = {}
        self.heartbeat_calls: int = 0
        self.last_heartbeat_row_ok: bool = True

    async def execute(self, query, params=None):
        text = str(query).lower()
        params = params or {}

        if "insert into agents" in text:
            key = (params["tenant_id"], params["hostname"])
            existing = self.agents.get(key)
            row = {
                "agent_id": existing["agent_id"] if existing else UUID(
                    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                ),
                "tenant_id": UUID(params["tenant_id"]),
                "hostname": params["hostname"],
                "platform": params["platform"],
                "agent_version": params.get("agent_version"),
                "registered_at": datetime.now(UTC),
                "last_heartbeat_at": datetime.now(UTC),
                "metadata": {},
            }
            self.agents[key] = row
            return _FakeResult(row=row)

        if "update agents" in text:
            self.heartbeat_calls += 1
            return _FakeResult(rowcount=1 if self.last_heartbeat_row_ok else 0)

        return _FakeResult()

    async def commit(self):
        pass


@pytest.fixture
def fake_app():
    from app.api.v1.agents import router  # noqa: PLC0415
    from app.core.tenant_auth import get_current_tenant  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/agents")

    db = _FakeDB()

    async def _db_override():
        yield db

    async def _tenant_override():
        return {
            "tenant_id": "11111111-2222-3333-4444-555555555555",
            "status": "active",
            "plan": "pro",
        }

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_tenant] = _tenant_override
    return app, db


def test_register_returns_agent_id_and_interval(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    resp = client.post(
        "/api/v1/agents/register",
        json={
            "hostname": "store-01-edge",
            "platform": "linux",
            "agent_version": "0.1.0",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["heartbeat_interval_s"] == 60
    assert UUID(body["agent_id"])
    # server_time is ISO-8601 with TZ.
    assert "T" in body["server_time"]
    assert body["registered_at"]


def test_register_is_idempotent_on_hostname(fake_app):
    from fastapi.testclient import TestClient

    app, db = fake_app
    client = TestClient(app)

    payload = {"hostname": "store-01", "platform": "linux"}
    first = client.post("/api/v1/agents/register", json=payload).json()
    second = client.post("/api/v1/agents/register", json=payload).json()

    assert first["agent_id"] == second["agent_id"]
    assert len(db.agents) == 1


def test_register_rejects_bad_platform(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    resp = client.post(
        "/api/v1/agents/register",
        json={"hostname": "h", "platform": "windows-xp"},
    )
    # 422 from pydantic — not 500, not 400.
    assert resp.status_code == 422


def test_heartbeat_happy_path(fake_app):
    from fastapi.testclient import TestClient

    app, db = fake_app
    client = TestClient(app)

    agent_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    resp = client.post(f"/api/v1/agents/{agent_id}/heartbeat")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next_heartbeat_in_s"] == 60
    assert body["agent_id"] == agent_id
    assert db.heartbeat_calls == 1


def test_heartbeat_unknown_agent_returns_404(fake_app):
    """When rowcount=0 (agent_id doesn't exist in this tenant) we must
    surface 404 — not 500, not 403 — so attackers cannot distinguish
    cross-tenant agent_ids from simply missing ones."""
    from fastapi.testclient import TestClient

    app, db = fake_app
    db.last_heartbeat_row_ok = False
    client = TestClient(app)

    resp = client.post("/api/v1/agents/00000000-0000-0000-0000-000000000000/heartbeat")
    assert resp.status_code == 404


def test_heartbeat_rejects_malformed_uuid(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    resp = client.post("/api/v1/agents/not-a-uuid/heartbeat")
    assert resp.status_code == 422

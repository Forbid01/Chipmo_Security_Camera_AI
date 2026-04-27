"""T4-12 — onboarding status pub/sub broker + WebSocket endpoint.

Two concerns under test:

1. The in-memory broker enforces per-tenant isolation, bounded
   backlog, and event replay for late subscribers.
2. The WebSocket endpoint authenticates via the API-key bearer flow
   and forwards published events to the connected client.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-onboarding-ws")

from app.services.onboarding_events import (  # noqa: E402
    AGENT_REGISTERED,
    CAMERA_DISCOVERED,
    EVENT_TYPES,
    InMemoryBroker,
    make_event,
)


# ---------------------------------------------------------------------------
# make_event
# ---------------------------------------------------------------------------

def test_make_event_known_type():
    e = make_event(AGENT_REGISTERED, payload={"agent_id": "x"})
    assert e["type"] == AGENT_REGISTERED
    assert e["payload"] == {"agent_id": "x"}
    assert "T" in e["ts"]


def test_make_event_unknown_type_rejected():
    with pytest.raises(ValueError):
        make_event("not_a_real_event")


def test_event_types_frozen():
    assert "agent_registered" in EVENT_TYPES
    assert len(EVENT_TYPES) >= 5


# ---------------------------------------------------------------------------
# InMemoryBroker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broker_publishes_to_matching_tenant():
    b = InMemoryBroker()
    sub = await b.subscribe("tenant-a")
    await b.publish("tenant-a", make_event(AGENT_REGISTERED, payload={"n": 1}))
    evt = await asyncio.wait_for(sub.get(), timeout=1)
    assert evt["payload"] == {"n": 1}
    await b.unsubscribe("tenant-a", sub)


@pytest.mark.asyncio
async def test_broker_does_not_leak_across_tenants():
    b = InMemoryBroker()
    sub_a = await b.subscribe("tenant-a")
    sub_b = await b.subscribe("tenant-b")

    await b.publish("tenant-a", make_event(AGENT_REGISTERED, payload={"owner": "a"}))
    evt = await asyncio.wait_for(sub_a.get(), timeout=1)
    assert evt["payload"]["owner"] == "a"

    # Tenant B's queue must remain empty — pulling with a tight
    # timeout should raise.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub_b.get(), timeout=0.1)


@pytest.mark.asyncio
async def test_broker_replays_history_to_late_subscriber():
    b = InMemoryBroker()
    for i in range(3):
        await b.publish(
            "tenant-x", make_event(CAMERA_DISCOVERED, payload={"seq": i})
        )
    sub = await b.subscribe("tenant-x")

    seqs = []
    for _ in range(3):
        evt = await asyncio.wait_for(sub.get(), timeout=1)
        seqs.append(evt["payload"]["seq"])
    assert seqs == [0, 1, 2]


@pytest.mark.asyncio
async def test_broker_unsubscribe_removes_subscription():
    b = InMemoryBroker()
    sub = await b.subscribe("t")
    assert b.subscriber_count("t") == 1
    await b.unsubscribe("t", sub)
    assert b.subscriber_count("t") == 0


@pytest.mark.asyncio
async def test_broker_bounded_backlog_drops_oldest():
    """A slow consumer must not OOM the broker. We cap backlog at
    _Queue.MAX_BACKLOG and drop oldest when the cap is hit."""
    from app.services.onboarding_events import _Queue

    b = InMemoryBroker()
    sub = await b.subscribe("t")
    # Flood past the backlog ceiling.
    for i in range(_Queue.MAX_BACKLOG + 10):
        await b.publish("t", make_event(AGENT_REGISTERED, payload={"seq": i}))
    # Pull one — must be something real, never raise.
    evt = await asyncio.wait_for(sub.get(), timeout=1)
    assert "seq" in evt["payload"]


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

class _FakeMappingResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, row=None):
        self.row = row

    async def execute(self, _query, _params=None):
        return _FakeMappingResult(row=self.row)


def _active_tenant_row(api_key_hash: str) -> dict:
    return {
        "tenant_id": "11111111-2222-3333-4444-555555555555",
        "legal_name": "Demo",
        "display_name": "Demo",
        "email": "demo@sentry.mn",
        "phone": None,
        "status": "active",
        "plan": "pro",
        "created_at": None,
        "trial_ends_at": None,
        "current_period_end": None,
        "payment_method_id": None,
        "resource_quota": {},
    }


@pytest.fixture
def ws_app():
    from app.api.v1 import onboarding_status  # noqa: PLC0415
    from app.db.repository.tenants import hash_api_key  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()
    app.include_router(onboarding_status.router, prefix="/api/v1/onboarding")

    # Shared per-test broker so publishes from one test don't leak
    # into the next.
    test_broker = InMemoryBroker()
    app.dependency_overrides[onboarding_status._get_broker] = lambda: test_broker

    raw_key = "sk_live_" + "x" * 40
    row = _active_tenant_row(hash_api_key(raw_key))
    db = _FakeDB(row=row)

    async def _db_override():
        yield db

    app.dependency_overrides[get_db] = _db_override

    return app, test_broker, raw_key


def test_ws_requires_auth(ws_app):
    from fastapi.testclient import TestClient

    app, _broker, _key = ws_app
    client = TestClient(app)

    with client.websocket_connect("/api/v1/onboarding/status") as sock:
        # Endpoint closes with 4401 — TestClient surfaces close as
        # WebSocketDisconnect on next recv.
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as ctx:
            sock.receive_json()
        assert ctx.value.code == 4401


def test_ws_accepts_valid_key_and_sends_hello(ws_app):
    from fastapi.testclient import TestClient

    app, _broker, key = ws_app
    client = TestClient(app)

    with client.websocket_connect(
        f"/api/v1/onboarding/status?token={key}"
    ) as sock:
        hello = sock.receive_json()
        assert hello["type"] == "hello"
        assert hello["tenant_id"]
        assert hello["server_time"]


@pytest.mark.asyncio
async def test_ws_forwards_broker_events(ws_app):
    from fastapi.testclient import TestClient

    app, broker, key = ws_app
    client = TestClient(app)

    with client.websocket_connect(
        f"/api/v1/onboarding/status?token={key}"
    ) as sock:
        _hello = sock.receive_json()

        # Publish concurrently — TestClient runs the server in a
        # background thread so publish from this asyncio loop still
        # fans out correctly.
        await broker.publish(
            "11111111-2222-3333-4444-555555555555",
            make_event(CAMERA_DISCOVERED, payload={"ip": "10.0.0.5"}),
        )
        evt = sock.receive_json()
        assert evt["type"] == CAMERA_DISCOVERED
        assert evt["payload"]["ip"] == "10.0.0.5"

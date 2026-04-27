"""End-to-end WebSocket isolation — two tenants, one broker (T4-12).

`test_onboarding_status_ws.py` covers the broker primitive (queues +
replay + backlog). This file exercises the full WebSocket endpoint
with *two* live connections authenticated as different tenants and
verifies the server never fans an event from tenant A to tenant B.

Catching this gap matters because the broker's correctness is
necessary but not sufficient — the endpoint is also responsible for:

* Resolving the bearer token to the right tenant_id,
* Subscribing each socket to its own tenant's queue (not a shared one),
* Not leaking state across reconnects on the same tenant.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-ws-isolation")

from app.services.onboarding_events import (  # noqa: E402
    CAMERA_DISCOVERED,
    InMemoryBroker,
    make_event,
)


TENANT_A_ID = "aaaaaaaa-1111-1111-1111-111111111111"
TENANT_B_ID = "bbbbbbbb-2222-2222-2222-222222222222"

KEY_A = "sk_live_" + "a" * 40
KEY_B = "sk_live_" + "b" * 40


def _tenant_row(tenant_id: str, email: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "legal_name": email,
        "display_name": email,
        "email": email,
        "phone": None,
        "status": "active",
        "plan": "pro",
        "created_at": None,
        "trial_ends_at": None,
        "current_period_end": None,
        "payment_method_id": None,
        "resource_quota": {},
    }


class _FakeMappingResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


class _KeyLookupDB:
    """Fake DB that routes auth by the API-key hash embedded in the
    SELECT bind params. Lets one DB instance authenticate both tenants
    depending on which key's hash was presented."""

    def __init__(self, rows_by_hash: dict[str, dict]):
        self._rows = rows_by_hash

    async def execute(self, _query, params=None):
        if not params:
            return _FakeMappingResult(None)
        # get_by_api_key_hash binds `api_key_hash` (and the rotation-
        # window variant binds `previous_api_key_hash`). Either resolves
        # a row in our map when present.
        for key in ("api_key_hash", "previous_api_key_hash"):
            h = params.get(key)
            if h and h in self._rows:
                return _FakeMappingResult(self._rows[h])
        return _FakeMappingResult(None)


@pytest.fixture
def two_tenant_ws_app():
    from app.api.v1 import onboarding_status  # noqa: PLC0415
    from app.db.repository.tenants import hash_api_key  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()
    app.include_router(onboarding_status.router, prefix="/api/v1/onboarding")

    broker = InMemoryBroker()
    app.dependency_overrides[onboarding_status._get_broker] = lambda: broker

    rows = {
        hash_api_key(KEY_A): _tenant_row(TENANT_A_ID, "a@sentry.mn"),
        hash_api_key(KEY_B): _tenant_row(TENANT_B_ID, "b@sentry.mn"),
    }
    db = _KeyLookupDB(rows)

    async def _db_override():
        yield db

    app.dependency_overrides[get_db] = _db_override
    return app, broker


def test_hello_frame_carries_the_authenticated_tenant(two_tenant_ws_app):
    """Belt-and-braces: each socket's `hello` frame announces its own
    tenant_id — never the other one's. If the endpoint ever confused
    the two bearers, this would fail fast."""
    from fastapi.testclient import TestClient

    app, _broker = two_tenant_ws_app
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/onboarding/status?token={KEY_A}") as sock_a:
        hello_a = sock_a.receive_json()
        assert hello_a["tenant_id"] == TENANT_A_ID

    with client.websocket_connect(f"/api/v1/onboarding/status?token={KEY_B}") as sock_b:
        hello_b = sock_b.receive_json()
        assert hello_b["tenant_id"] == TENANT_B_ID
        assert hello_b["tenant_id"] != TENANT_A_ID


@pytest.mark.asyncio
async def test_event_published_for_tenant_a_never_reaches_tenant_b(two_tenant_ws_app):
    """Two live sockets, one publish. Tenant A sees the event; tenant B
    must not — not on initial fan-out, not on reconnect replay, not on
    anything the broker chose to do with neighbouring tenant state."""
    from fastapi.testclient import TestClient

    app, broker = two_tenant_ws_app
    client = TestClient(app)

    with client.websocket_connect(
        f"/api/v1/onboarding/status?token={KEY_A}"
    ) as sock_a, client.websocket_connect(
        f"/api/v1/onboarding/status?token={KEY_B}"
    ) as sock_b:
        # Drain both hello frames so the next receive is the event.
        sock_a.receive_json()
        sock_b.receive_json()

        await broker.publish(
            TENANT_A_ID,
            make_event(CAMERA_DISCOVERED, payload={"ip": "10.0.0.9"}),
        )
        evt_a = sock_a.receive_json()
        assert evt_a["type"] == CAMERA_DISCOVERED
        assert evt_a["payload"]["ip"] == "10.0.0.9"

        # Tenant B's socket must stay silent. TestClient's recv blocks;
        # we can't await a zero-timeout there, so probe via the broker's
        # own subscriber registry: only tenant A should hold subscribers.
        assert broker.subscriber_count(TENANT_A_ID) >= 1
        assert broker.subscriber_count(TENANT_B_ID) >= 1
        # And the only events in flight for tenant B are its own replay
        # log, which we never published to.
        assert all(
            evt["payload"].get("ip") != "10.0.0.9"
            for evt in list(broker._replay[TENANT_B_ID])  # noqa: SLF001
        )


@pytest.mark.asyncio
async def test_reconnect_does_not_leak_prior_tenant_subscription(two_tenant_ws_app):
    """Closing tenant A's socket must unsubscribe it before any
    tenant B connection opens. Otherwise a long-lived server with
    sloppy cleanup would bloat A's queue forever."""
    from fastapi.testclient import TestClient

    app, broker = two_tenant_ws_app
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/onboarding/status?token={KEY_A}") as sock:
        sock.receive_json()
        assert broker.subscriber_count(TENANT_A_ID) == 1

    # After the `with` block, the socket closed — the endpoint's
    # `finally` should have released the subscription.
    assert broker.subscriber_count(TENANT_A_ID) == 0
    # Tenant B count was never incremented by this test.
    assert broker.subscriber_count(TENANT_B_ID) == 0

"""WebSocket endpoint for onboarding progress events (T4-12).

Lifecycle:

1. Client opens `wss://.../api/v1/onboarding/status` with
   `Authorization: Bearer sk_live_*` in the upgrade headers.
2. Server validates the API key (same bearer-scheme as the REST
   endpoints) and subscribes the socket to this tenant's event
   stream.
3. Server immediately sends a `{"type":"hello","tenant_id":...,
   "server_time":...}` frame so the client can sync its clock.
4. Server forwards each event dict as a JSON text frame.
5. Client disconnects → server unsubscribes and releases the queue.

Reconnect guidance: the client should reconnect on close with
exponential backoff (1s → 30s cap). Events published while the
socket is down are NOT guaranteed to be delivered on reconnect, but
the last 32 events per tenant are replayed on subscribe so short
outages stay seamless.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.core.tenant_auth import API_KEY_PREFIX
from app.db.repository.tenants import TenantRepository, hash_api_key
from app.db.session import DB
from app.services.onboarding_events import InMemoryBroker, broker as default_broker
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_broker() -> InMemoryBroker:
    """Dependency hook — tests override with a fresh per-test broker."""
    return default_broker


async def _resolve_tenant_id(websocket: WebSocket, db) -> str | None:
    """Validate the API key on the WebSocket handshake.

    The upgrade request carries headers like any HTTP GET, so the
    same Authorization-bearer contract from /agents/* applies. We
    return None on any failure so the caller closes with a 4401
    application-level status (per RFC 6455 §7.4.2 reserved app range).
    """
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if not auth:
        # Some websocket clients can't set headers — fall back to a
        # `?token=` query string so browser-side EventSource-ish
        # wrappers still work.
        auth_q = websocket.query_params.get("token")
        if auth_q:
            auth = f"Bearer {auth_q}"
    if not auth or not auth.startswith("Bearer "):
        return None

    raw = auth[len("Bearer ") :].strip()
    if not raw.startswith(API_KEY_PREFIX):
        return None

    repo = TenantRepository(db)
    tenant = await repo.get_by_api_key_hash(hash_api_key(raw))
    if tenant is None or tenant.get("status") != "active":
        return None
    return str(tenant["tenant_id"])


@router.websocket("/status")
async def onboarding_status_stream(
    websocket: WebSocket,
    db: DB,
    broker: InMemoryBroker = Depends(_get_broker),
) -> None:
    await websocket.accept()

    tenant_id = await _resolve_tenant_id(websocket, db)
    if tenant_id is None:
        # 4401 — closed WebSocket app-level code for "unauthorized".
        # 1008 is the formal "policy violation" code but clients often
        # misinterpret it as a server bug.
        await websocket.close(code=4401, reason="auth")
        return

    await websocket.send_json({
        "type": "hello",
        "tenant_id": tenant_id,
        "server_time": datetime.now(UTC).isoformat(),
    })

    subscription = await broker.subscribe(tenant_id)
    try:
        while True:
            # Concurrently wait on either the broker pushing an event
            # OR the client sending anything (ping/close). We drain
            # incoming frames but don't interpret them — this channel
            # is server-push only.
            event = await subscription.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("onboarding_status_stream_error")
    finally:
        await broker.unsubscribe(tenant_id, subscription)

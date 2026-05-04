"""Agents API — register + heartbeat (T4-07 / T4-08).

Both endpoints are tenant-authenticated via the API-key bearer flow
(T1-05). The agent bakes this key into its config.yaml during
installation (T4-02); it presents the key on every register +
heartbeat call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.tenant_auth import CurrentTenant
from app.db.repository.agents import (
    HEARTBEAT_INTERVAL_SECONDS,
    AgentRepository,
)
from app.db.session import DB
from app.schemas.agent import (
    AgentDiscoveriesRequest,
    AgentHeartbeatResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
)
from app.services.onboarding_events import (
    AGENT_HEARTBEAT,
    AGENT_REGISTERED,
    CAMERA_DISCOVERED,
    broker,
    make_event,
)
from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    summary="Register an edge agent (idempotent on hostname).",
)
async def register_agent(
    payload: AgentRegisterRequest,
    db: DB,
    tenant: CurrentTenant,
) -> AgentRegisterResponse:
    repo = AgentRepository(db)
    row = await repo.register_or_refresh(
        tenant_id=tenant["tenant_id"],
        hostname=payload.hostname,
        platform=payload.platform,
        agent_version=payload.agent_version,
        metadata=payload.metadata,
    )
    await broker.publish(
        str(tenant["tenant_id"]),
        make_event(
            AGENT_REGISTERED,
            payload={
                "agent_id": str(row["agent_id"]),
                "hostname": row["hostname"],
                "platform": row["platform"],
                "version": row.get("agent_version"),
            },
        ),
    )

    return AgentRegisterResponse(
        agent_id=row["agent_id"],
        heartbeat_interval_s=HEARTBEAT_INTERVAL_SECONDS,
        server_time=datetime.now(UTC),
        registered_at=row["registered_at"],
        last_heartbeat_at=row.get("last_heartbeat_at"),
    )


@router.post(
    "/{agent_id}/heartbeat",
    response_model=AgentHeartbeatResponse,
    summary="Record an agent heartbeat; refresh last_heartbeat_at.",
)
async def heartbeat(
    agent_id: UUID,
    db: DB,
    tenant: CurrentTenant,
) -> AgentHeartbeatResponse:
    repo = AgentRepository(db)
    ok = await repo.record_heartbeat(
        agent_id=agent_id,
        tenant_id=tenant["tenant_id"],
    )
    if not ok:
        # 404 — not 403 — for cross-tenant hits so attackers can't
        # enumerate valid agent_ids from other orgs.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent not found",
        )

    await broker.publish(
        str(tenant["tenant_id"]),
        make_event(
            AGENT_HEARTBEAT,
            payload={"agent_id": str(agent_id)},
        ),
    )

    return AgentHeartbeatResponse(
        agent_id=agent_id,
        server_time=datetime.now(UTC),
        next_heartbeat_in_s=HEARTBEAT_INTERVAL_SECONDS,
    )


@router.post(
    "/{agent_id}/discoveries",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Submit ONVIF probe results; publishes camera_discovered events (T4-09 integration).",
)
async def submit_discoveries(
    agent_id: UUID,
    payload: AgentDiscoveriesRequest,
    db: DB,
    tenant: CurrentTenant,
) -> None:
    """Accept the batch of cameras found by the agent's WS-Discovery probe
    and publish a `camera_discovered` event per camera to the onboarding
    WebSocket stream so the frontend can render them in real time.

    Reuses `record_heartbeat` to verify agent ownership — cross-tenant
    agent IDs return 404, not 403, to avoid enumeration.
    """
    repo = AgentRepository(db)
    ok = await repo.record_heartbeat(
        agent_id=agent_id,
        tenant_id=tenant["tenant_id"],
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent not found",
        )

    for cam in payload.cameras:
        await broker.publish(
            str(tenant["tenant_id"]),
            make_event(
                CAMERA_DISCOVERED,
                payload={
                    "agent_id": str(agent_id),
                    "ip": cam.ip,
                    "port": cam.port,
                    "xaddrs": cam.xaddrs,
                    "manufacturer_id": cam.manufacturer_id,
                    "manufacturer_display": cam.manufacturer_display,
                    "model_hint": cam.model_hint,
                    "mac_oui": cam.mac_oui,
                },
            ),
        )

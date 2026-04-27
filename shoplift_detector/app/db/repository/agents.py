"""Data access for the `agents` table (T4-07 / T4-08).

Two access paths:

* `register_or_refresh` — idempotent upsert on (tenant_id, hostname).
  Restarts don't mint a new agent_id, they just refresh metadata +
  registered_at markers.
* `record_heartbeat` — no-op UPSERT on last_heartbeat_at for the
  /heartbeat endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Agents are considered offline once their last heartbeat is older
# than this. Kept on the class so T4-08 endpoint + dashboard share
# the same threshold.
OFFLINE_THRESHOLD_SECONDS = 300   # 5 minutes

# Agents are expected to beat at this cadence.
HEARTBEAT_INTERVAL_SECONDS = 60


class AgentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_or_refresh(
        self,
        *,
        tenant_id: UUID | str,
        hostname: str,
        platform: str,
        agent_version: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a new agent row or refresh the existing one.

        The `UNIQUE(tenant_id, hostname)` constraint is exploited via
        ON CONFLICT so a crashed + restarted agent keeps its agent_id
        stable. metadata JSON is replaced (not merged) on re-register.
        """
        import json

        params = {
            "tenant_id": str(tenant_id),
            "hostname": hostname,
            "platform": platform,
            "agent_version": agent_version,
            "metadata": json.dumps(metadata or {}),
        }
        query = text(
            """
            INSERT INTO agents (
                tenant_id, hostname, platform, agent_version, metadata,
                registered_at, last_heartbeat_at
            )
            VALUES (
                CAST(:tenant_id AS UUID), :hostname, :platform,
                :agent_version, CAST(:metadata AS JSONB),
                now(), now()
            )
            ON CONFLICT (tenant_id, hostname) DO UPDATE SET
                platform          = EXCLUDED.platform,
                agent_version     = EXCLUDED.agent_version,
                metadata          = EXCLUDED.metadata,
                registered_at     = now(),
                last_heartbeat_at = now()
            RETURNING agent_id, tenant_id, hostname, platform,
                      agent_version, registered_at, last_heartbeat_at,
                      metadata
            """
        )
        result = await self.db.execute(query, params)
        row = dict(result.mappings().fetchone())
        await self.db.commit()
        return row

    async def record_heartbeat(
        self,
        *,
        agent_id: UUID | str,
        tenant_id: UUID | str,
        now: datetime | None = None,
    ) -> bool:
        """Update last_heartbeat_at. Returns True on a real row hit,
        False when the agent_id doesn't exist or belongs to a
        different tenant — the handler maps that to 404.
        """
        query = text(
            """
            UPDATE agents
               SET last_heartbeat_at = COALESCE(:now, now())
             WHERE agent_id  = CAST(:agent_id AS UUID)
               AND tenant_id = CAST(:tenant_id AS UUID)
            """
        )
        result = await self.db.execute(
            query,
            {
                "agent_id": str(agent_id),
                "tenant_id": str(tenant_id),
                "now": now,
            },
        )
        await self.db.commit()
        return result.rowcount > 0

    async def get(
        self,
        *,
        agent_id: UUID | str,
        tenant_id: UUID | str,
    ) -> dict[str, Any] | None:
        query = text(
            """
            SELECT agent_id, tenant_id, hostname, platform,
                   agent_version, registered_at, last_heartbeat_at,
                   metadata
              FROM agents
             WHERE agent_id  = CAST(:agent_id AS UUID)
               AND tenant_id = CAST(:tenant_id AS UUID)
             LIMIT 1
            """
        )
        result = await self.db.execute(
            query,
            {"agent_id": str(agent_id), "tenant_id": str(tenant_id)},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


def derive_status(
    last_heartbeat_at: datetime | None,
    *,
    now: datetime,
    threshold_seconds: int = OFFLINE_THRESHOLD_SECONDS,
) -> str:
    """Map a heartbeat timestamp to a status string for UI display.

    Keeping this pure makes it easy to reuse from the admin dashboard
    without an extra round trip to compute the same field.
    """
    if last_heartbeat_at is None:
        return "pending"
    if last_heartbeat_at.tzinfo is None:
        # Older migrations accidentally stored naive timestamps —
        # assume UTC rather than erroring out the whole dashboard.
        from datetime import UTC
        last_heartbeat_at = last_heartbeat_at.replace(tzinfo=UTC)
    age = (now - last_heartbeat_at).total_seconds()
    if age > threshold_seconds:
        return "offline"
    return "online"


__all__ = [
    "HEARTBEAT_INTERVAL_SECONDS",
    "OFFLINE_THRESHOLD_SECONDS",
    "AgentRepository",
    "derive_status",
]

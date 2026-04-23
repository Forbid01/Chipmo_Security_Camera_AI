"""Data access for audit_log table.

`log()` is the single entry point service code should use. It enforces:
- exactly one of resource_int_id / resource_uuid / resource_key is set
  when resource_type is provided
- details JSONB is serialized via `json.dumps` so non-str values round-trip

Query helpers cover the common audit-review shapes: by user, by resource,
by action, recent across the system. `delete_older_than_days` provides a
manual retention until TimescaleDB policy is wired up (T02-07).
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AuditLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _validate_resource(
        resource_type: str | None,
        resource_int_id: int | None,
        resource_uuid: UUID | str | None,
        resource_key: str | None,
    ) -> None:
        provided = [
            x is not None
            for x in (resource_int_id, resource_uuid, resource_key)
        ]
        filled = sum(provided)
        if resource_type is None:
            if filled > 0:
                raise ValueError(
                    "resource_type is required when a resource id/key is given"
                )
            return
        if filled > 1:
            raise ValueError(
                "Pass at most one of resource_int_id, resource_uuid, resource_key"
            )

    async def log(
        self,
        *,
        action: str,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_int_id: int | None = None,
        resource_uuid: UUID | str | None = None,
        resource_key: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        timestamp: datetime | None = None,
    ) -> int:
        """Insert an audit row; returns the new row id."""
        if not action:
            raise ValueError("action is required")
        self._validate_resource(
            resource_type, resource_int_id, resource_uuid, resource_key
        )

        ts = self._normalize_datetime(timestamp) if timestamp else None
        params: dict[str, Any] = {
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_int_id": resource_int_id,
            "resource_uuid": str(resource_uuid) if resource_uuid else None,
            "resource_key": resource_key,
            "details": json.dumps(details or {}),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": ts,
        }

        timestamp_clause = (
            ":timestamp"
            if ts is not None
            else "now()"
        )
        query = text(f"""
            INSERT INTO audit_log (
                user_id,
                action,
                resource_type,
                resource_int_id,
                resource_uuid,
                resource_key,
                details,
                ip_address,
                user_agent,
                timestamp
            )
            VALUES (
                :user_id,
                :action,
                :resource_type,
                :resource_int_id,
                CAST(:resource_uuid AS UUID),
                :resource_key,
                CAST(:details AS JSONB),
                :ip_address,
                :user_agent,
                {timestamp_clause}
            )
            RETURNING id
        """)
        result = await self.db.execute(query, params)
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else 0

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT *
            FROM audit_log
            WHERE user_id = :user_id
            ORDER BY timestamp DESC
            LIMIT :limit
        """)
        result = await self.db.execute(
            query, {"user_id": user_id, "limit": limit}
        )
        return [dict(row) for row in result.mappings().fetchall()]

    async def list_for_resource(
        self,
        resource_type: str,
        *,
        resource_int_id: int | None = None,
        resource_uuid: UUID | str | None = None,
        resource_key: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._validate_resource(
            resource_type, resource_int_id, resource_uuid, resource_key
        )

        conditions = ["resource_type = :resource_type"]
        params: dict[str, Any] = {
            "resource_type": resource_type,
            "limit": limit,
        }
        if resource_int_id is not None:
            conditions.append("resource_int_id = :resource_int_id")
            params["resource_int_id"] = resource_int_id
        if resource_uuid is not None:
            conditions.append("resource_uuid = CAST(:resource_uuid AS UUID)")
            params["resource_uuid"] = str(resource_uuid)
        if resource_key is not None:
            conditions.append("resource_key = :resource_key")
            params["resource_key"] = resource_key

        query = text(f"""
            SELECT *
            FROM audit_log
            WHERE {" AND ".join(conditions)}
            ORDER BY timestamp DESC
            LIMIT :limit
        """)
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().fetchall()]

    async def list_by_action(
        self,
        action: str,
        *,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"action": action, "limit": limit}
        since_clause = ""
        if since is not None:
            params["since"] = self._normalize_datetime(since)
            since_clause = "AND timestamp >= :since"

        query = text(f"""
            SELECT *
            FROM audit_log
            WHERE action = :action
              {since_clause}
            ORDER BY timestamp DESC
            LIMIT :limit
        """)
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().fetchall()]

    async def list_recent(
        self,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT *
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT :limit
        """)
        result = await self.db.execute(query, {"limit": limit})
        return [dict(row) for row in result.mappings().fetchall()]

    async def delete_older_than(self, cutoff: datetime) -> int:
        cutoff = self._normalize_datetime(cutoff)
        query = text("DELETE FROM audit_log WHERE timestamp < :cutoff")
        result = await self.db.execute(query, {"cutoff": cutoff})
        await self.db.commit()
        return result.rowcount

    async def delete_older_than_days(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return await self.delete_older_than(cutoff)

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

"""Pydantic schemas for agent register + heartbeat (T4-07 / T4-08)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

HostnameStr = Annotated[str, StringConstraints(min_length=1, max_length=253)]
VersionStr = Annotated[str, StringConstraints(max_length=64)]


class AgentRegisterRequest(BaseModel):
    hostname: HostnameStr
    platform: Literal["linux", "windows", "macos"]
    agent_version: VersionStr | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRegisterResponse(BaseModel):
    """The agent uses the three non-audit fields to configure its own
    lifecycle — heartbeat loop + clock skew guard."""

    agent_id: UUID
    heartbeat_interval_s: int
    server_time: datetime
    registered_at: datetime
    last_heartbeat_at: datetime | None = None


class AgentHeartbeatResponse(BaseModel):
    """Heartbeat is a no-op for the client beyond "refresh last seen" —
    but we echo server_time so the agent can detect and log clock
    drift, and the next-heartbeat-at hint lets it back-off cleanly
    if we ever need to stretch the interval."""

    agent_id: UUID
    server_time: datetime
    next_heartbeat_in_s: int

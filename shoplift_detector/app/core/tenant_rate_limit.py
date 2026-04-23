"""Per-tenant token-bucket rate limit (T1-08).

Design goals:
- Plan-based quota (Starter 30/min, Pro 60/min, Enterprise 600/min).
- Pluggable backend — Redis in production (T1-12 deploys the real
  client), in-memory fallback for single-worker dev / tests.
- Deterministic response shape: 429 + `Retry-After` seconds matching
  the minute bucket reset.

The bucket key is `ratelimit:{tenant_id}:{action}:{minute_bucket}`
(per DOC-05 §5.2). `minute_bucket` is `int(now_epoch // 60)` — rolls
over every 60 seconds, so the worst case for a client that burst-hits
right before the boundary is one extra minute of retries.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, status

# Plan → requests per minute. Matches DOC-05 §5.2 / 07_Tasks T1-08.
PLAN_RATE_LIMITS: dict[str, int] = {
    "trial": 30,
    "starter": 30,
    "pro": 60,
    "enterprise": 600,
}

DEFAULT_RATE_LIMIT = 30  # used when plan is missing / unknown
BUCKET_WINDOW_SECONDS = 60


class RateLimitBackend(Protocol):
    """Counter abstraction so the limiter can swap Redis ↔ in-memory."""

    async def incr(self, key: str, ttl_seconds: int) -> int: ...


class InMemoryBackend:
    """Process-local counter. Fine for a single-worker dev stack and
    every unit test. Production swaps in a Redis-backed implementation
    because multi-worker deploys need a shared counter."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._expires: dict[str, float] = {}

    async def incr(self, key: str, ttl_seconds: int) -> int:
        now = time.monotonic()
        # Lazy expiry — cheaper than a sweeper thread.
        exp = self._expires.get(key)
        if exp is not None and exp <= now:
            self._counts.pop(key, None)
            self._expires.pop(key, None)
        self._counts[key] += 1
        # Only (re)set TTL on first hit of the bucket so later
        # increments don't extend the window.
        self._expires.setdefault(key, now + ttl_seconds)
        return self._counts[key]


@dataclass(frozen=True)
class RateLimitResult:
    """Returned by `check()` so handlers can stamp X-RateLimit-* headers."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


def _minute_bucket(now_epoch: float | None = None) -> int:
    t = now_epoch if now_epoch is not None else time.time()
    return int(t) // BUCKET_WINDOW_SECONDS


def _seconds_until_next_bucket(now_epoch: float | None = None) -> int:
    t = now_epoch if now_epoch is not None else time.time()
    return BUCKET_WINDOW_SECONDS - (int(t) % BUCKET_WINDOW_SECONDS)


class TenantRateLimiter:
    """Façade that callers (FastAPI deps, workers) use. Lookup of the
    plan limit is inlined here so tests can replace the backend
    without patching the plan table."""

    def __init__(
        self,
        backend: RateLimitBackend | None = None,
        *,
        plan_limits: dict[str, int] | None = None,
    ):
        self._backend = backend or InMemoryBackend()
        self._plan_limits = plan_limits or PLAN_RATE_LIMITS

    def _limit_for(self, plan: str | None) -> int:
        if plan is None:
            return DEFAULT_RATE_LIMIT
        return self._plan_limits.get(plan, DEFAULT_RATE_LIMIT)

    async def check(
        self,
        tenant_id: str,
        *,
        plan: str | None,
        action: str = "api_call",
        now_epoch: float | None = None,
    ) -> RateLimitResult:
        limit = self._limit_for(plan)
        bucket = _minute_bucket(now_epoch)
        key = f"ratelimit:{tenant_id}:{action}:{bucket}"
        count = await self._backend.incr(key, ttl_seconds=BUCKET_WINDOW_SECONDS)
        retry_after = _seconds_until_next_bucket(now_epoch)
        if count > limit:
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                retry_after_seconds=retry_after,
            )
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=retry_after,
        )

    async def enforce(
        self,
        tenant_id: str,
        *,
        plan: str | None,
        action: str = "api_call",
        now_epoch: float | None = None,
    ) -> RateLimitResult:
        """Raise 429 with Retry-After if the bucket is full.

        Call from FastAPI deps that sit between `get_current_tenant`
        and the handler. The returned result can still be used to
        stamp X-RateLimit-* response headers on success.
        """
        result = await self.check(
            tenant_id, plan=plan, action=action, now_epoch=now_epoch
        )
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "limit": result.limit,
                    "retry_after_seconds": result.retry_after_seconds,
                    "message_mn": "Хэт олон хүсэлт. Түр хүлээнэ үү.",
                },
                headers={"Retry-After": str(result.retry_after_seconds)},
            )
        return result


# Module-level singleton — handlers/DI import this so every request
# shares one bucket state. Tests instantiate their own `TenantRateLimiter`
# with a fresh backend.
tenant_rate_limiter = TenantRateLimiter()


async def enforce_tenant_rate_limit(
    tenant: dict[str, Any],
) -> RateLimitResult:
    """FastAPI dependency — wires `get_current_tenant` to the module
    singleton. Mount after `get_current_tenant` in handler chains:

        @router.get("/path")
        async def h(tenant: CurrentTenant, _: RateLimited): ...
    """
    return await tenant_rate_limiter.enforce(
        tenant_id=str(tenant["tenant_id"]),
        plan=tenant.get("plan"),
    )

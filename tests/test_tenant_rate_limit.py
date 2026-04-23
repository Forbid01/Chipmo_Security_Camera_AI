"""Tests for T1-08 — per-tenant token-bucket rate limit."""

import pytest
from fastapi import HTTPException

from shoplift_detector.app.core.tenant_rate_limit import (
    BUCKET_WINDOW_SECONDS,
    DEFAULT_RATE_LIMIT,
    PLAN_RATE_LIMITS,
    InMemoryBackend,
    TenantRateLimiter,
)


@pytest.mark.parametrize("plan,limit", [
    ("trial", 30),
    ("starter", 30),
    ("pro", 60),
    ("enterprise", 600),
])
def test_plan_rate_limits_match_doc(plan, limit):
    assert PLAN_RATE_LIMITS[plan] == limit


def _fresh_limiter() -> TenantRateLimiter:
    # Every test gets its own backend instance to avoid cross-test
    # state leakage.
    return TenantRateLimiter(backend=InMemoryBackend())


# ---------------------------------------------------------------------------
# check() — returning shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_hit_is_allowed_with_remaining_budget():
    limiter = _fresh_limiter()
    result = await limiter.check("t-1", plan="pro")
    assert result.allowed is True
    assert result.limit == 60
    assert result.remaining == 59


@pytest.mark.asyncio
async def test_unknown_plan_uses_default_limit():
    limiter = _fresh_limiter()
    result = await limiter.check("t-1", plan="legacy")
    assert result.limit == DEFAULT_RATE_LIMIT


@pytest.mark.asyncio
async def test_null_plan_uses_default_limit():
    limiter = _fresh_limiter()
    result = await limiter.check("t-1", plan=None)
    assert result.limit == DEFAULT_RATE_LIMIT


# ---------------------------------------------------------------------------
# Bucket counting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_starter_blocks_at_31st_hit_in_one_minute():
    limiter = _fresh_limiter()
    # Pin clock so all 31 hits land in the same minute bucket.
    epoch = 1_000_000_000.0
    for i in range(30):
        result = await limiter.check("t-1", plan="starter", now_epoch=epoch)
        assert result.allowed is True, f"hit {i + 1} should pass"
    result = await limiter.check("t-1", plan="starter", now_epoch=epoch)
    assert result.allowed is False
    assert result.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_new_bucket_resets_the_counter():
    limiter = _fresh_limiter()
    epoch = 1_000_000_000.0  # aligned to minute boundary
    # Fill the bucket.
    for _ in range(30):
        await limiter.check("t-1", plan="starter", now_epoch=epoch)
    blocked = await limiter.check("t-1", plan="starter", now_epoch=epoch)
    assert blocked.allowed is False
    # Advance to the next bucket — the limiter's in-memory backend
    # uses monotonic time for TTL, so we bump by a full window.
    next_epoch = epoch + BUCKET_WINDOW_SECONDS
    result = await limiter.check("t-1", plan="starter", now_epoch=next_epoch)
    assert result.allowed is True


@pytest.mark.asyncio
async def test_tenants_do_not_share_buckets():
    limiter = _fresh_limiter()
    epoch = 1_000_000_000.0
    # Exhaust tenant A.
    for _ in range(30):
        await limiter.check("tenant-a", plan="starter", now_epoch=epoch)
    # Tenant B must still have a full bucket.
    result = await limiter.check("tenant-b", plan="starter", now_epoch=epoch)
    assert result.allowed is True
    assert result.remaining == 29


# ---------------------------------------------------------------------------
# enforce() — 429 handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_raises_429_with_retry_after_header():
    limiter = _fresh_limiter()
    epoch = 1_000_000_000.0
    for _ in range(30):
        await limiter.enforce("t-1", plan="starter", now_epoch=epoch)
    with pytest.raises(HTTPException) as ctx:
        await limiter.enforce("t-1", plan="starter", now_epoch=epoch)
    err = ctx.value
    assert err.status_code == 429
    assert "Retry-After" in err.headers
    assert int(err.headers["Retry-After"]) > 0
    assert err.detail["error"] == "rate_limit_exceeded"
    assert err.detail["limit"] == 30


# ---------------------------------------------------------------------------
# Action scoping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_different_actions_have_independent_buckets():
    limiter = _fresh_limiter()
    epoch = 1_000_000_000.0
    for _ in range(30):
        await limiter.check(
            "t-1", plan="starter", action="api_call", now_epoch=epoch
        )
    # Different action → fresh bucket.
    result = await limiter.check(
        "t-1", plan="starter", action="webhook", now_epoch=epoch
    )
    assert result.allowed is True


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_in_memory_backend_returns_running_count():
    backend = InMemoryBackend()
    a = await backend.incr("k", ttl_seconds=60)
    b = await backend.incr("k", ttl_seconds=60)
    c = await backend.incr("k", ttl_seconds=60)
    assert (a, b, c) == (1, 2, 3)

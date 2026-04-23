"""Central rate-limit configuration.

One shared `Limiter` instance so decorators across the codebase use
the same storage backend and response header policy. Rate categories
below come from docs/07-API-SPEC.md §7.

Storage backend:
- `REDIS_URL` or `RATE_LIMIT_REDIS_URL` set → Redis. Counters survive
  restarts and work across multiple uvicorn workers.
- Otherwise → in-memory (per-worker). Fine for dev / single-process
  deploys.

Key function:
- Authenticated requests key off the JWT user id (so dashboard limits
  are per-user).
- Anonymous / pre-auth requests fall back to client IP (so login and
  password-reset limits are per-source).

Headers:
- `headers_enabled=True` makes the limiter emit X-RateLimit-Limit /
  X-RateLimit-Remaining / X-RateLimit-Reset on decorated responses.
- `SlowAPIMiddleware` (installed in main.py) propagates those headers
  through FastAPI's response pipeline and appends Retry-After on 429.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


# Rate categories per docs/07-API-SPEC.md §7. String values are the
# slowapi limit expression; use them with `@limiter.limit(CATEGORY)`.
class RateLimits:
    EDGE_HEARTBEAT = "120/minute"       # 2x buffer over 1 heartbeat / 30s
    EDGE_ALERTS = "300/minute"          # burst capacity for batch uploads
    AUTH_LOGIN = "10/minute"            # per IP
    AUTH_PASSWORD_RESET = "5/minute"    # per IP
    DASHBOARD_READ = "1000/minute"      # per user
    DASHBOARD_WRITE = "200/minute"      # per user


RATE_LIMIT_CATEGORIES: tuple[str, ...] = (
    RateLimits.EDGE_HEARTBEAT,
    RateLimits.EDGE_ALERTS,
    RateLimits.AUTH_LOGIN,
    RateLimits.AUTH_PASSWORD_RESET,
    RateLimits.DASHBOARD_READ,
    RateLimits.DASHBOARD_WRITE,
)


def _rate_limit_storage_uri() -> str | None:
    """Pick the Redis URL from the env, accepting either of two names."""
    for env_var in ("RATE_LIMIT_REDIS_URL", "REDIS_URL"):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value
    return None


def _rate_limit_key(request: Request) -> str:
    """Prefer the JWT user id; fall back to client IP.

    The auth middleware stashes the authenticated user dict on
    `request.state.user` when the request carried a valid cookie or
    bearer token. Using that as the key means a single user can't
    bypass per-user limits by spinning up many IPs, and multiple users
    behind a shared NAT don't starve each other on per-IP limits.
    """
    user: dict[str, Any] | None = getattr(request.state, "user", None)
    if isinstance(user, dict):
        user_id = user.get("user_id") or user.get("sub")
        if user_id is not None:
            return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


def build_limiter() -> Limiter:
    storage_uri = _rate_limit_storage_uri()
    if storage_uri:
        logger.info("Rate limiter using Redis backend")
    else:
        logger.info(
            "Rate limiter using in-memory backend (no REDIS_URL configured). "
            "Counters do not survive restarts or span workers."
        )
    return Limiter(
        key_func=_rate_limit_key,
        storage_uri=storage_uri,
        headers_enabled=True,
        swallow_errors=True,
        strategy="fixed-window",
    )


# Module-level singleton. Import this from main.py, auth.py, and any
# endpoint that wants @limiter.limit(...). Never create a second
# Limiter — slowapi expects exactly one per app.
limiter: Limiter = build_limiter()

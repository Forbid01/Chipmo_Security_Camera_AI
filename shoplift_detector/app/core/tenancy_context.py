"""Per-request tenant context for RLS GUC population.

This is the upstream half of the Layer-2 (Postgres RLS) defense
designed in T02-24. The downstream half — the SQLAlchemy event hook
that actually writes `SET LOCAL app.current_org_id` / `app.bypass_tenant`
at transaction begin — lives in `app.db.tenancy_events` and reads
from the ContextVars defined here.

Contract:

- `current_tenant_org_id` holds the authenticated user's organization
  id. `None` means "no tenant asserted" — the event hook will fail
  closed to `-1` so RLS policies cannot match any row.
- `current_tenant_bypass` is `True` only for super-admin paths that
  legitimately need to see every tenant's data.
- ContextVars are thread-safe AND task-safe — an asyncio task sees
  its own value, not another task's, even when multiple requests are
  interleaved on the same event loop.

The FastAPI dependency `apply_tenant_context` is intended to be hung
on the main API router so every authenticated request populates the
context before its handler runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

# Sentinels used by the event hook to produce the three possible states
# via a single ContextVar read. See `app.db.tenancy_events`.

current_tenant_org_id: ContextVar[int | None] = ContextVar(
    "current_tenant_org_id", default=None
)
current_tenant_bypass: ContextVar[bool] = ContextVar(
    "current_tenant_bypass", default=False
)


def set_tenant_context(user: dict[str, Any] | None) -> tuple[Token, Token]:
    """Populate the ContextVars from a CurrentUser dict.

    Returns the two reset Tokens so callers can restore the previous
    values symmetrically. Most call sites should use
    :func:`tenant_context` (a context manager) instead of managing the
    tokens directly.
    """
    if user is None:
        org_token = current_tenant_org_id.set(None)
        bypass_token = current_tenant_bypass.set(False)
        return org_token, bypass_token

    if user.get("role") == "super_admin":
        org_token = current_tenant_org_id.set(None)
        bypass_token = current_tenant_bypass.set(True)
        return org_token, bypass_token

    org_id = user.get("org_id")
    # Coerce to int so the SET LOCAL serialization later doesn't have
    # to re-validate. None is a legal value and means "fail closed".
    org_value: int | None = int(org_id) if isinstance(org_id, int) else None
    org_token = current_tenant_org_id.set(org_value)
    bypass_token = current_tenant_bypass.set(False)
    return org_token, bypass_token


def reset_tenant_context(tokens: tuple[Token, Token]) -> None:
    org_token, bypass_token = tokens
    current_tenant_org_id.reset(org_token)
    current_tenant_bypass.reset(bypass_token)


@contextmanager
def tenant_context(user: dict[str, Any] | None) -> Iterator[None]:
    """Scoped population of the two ContextVars.

    Useful for code paths that run outside a FastAPI request (e.g.
    background workers, scripts) and want to issue DB queries under a
    specific tenant.
    """
    tokens = set_tenant_context(user)
    try:
        yield
    finally:
        reset_tenant_context(tokens)


def snapshot() -> dict[str, Any]:
    """Return the current context as a dict (diagnostic helper)."""
    return {
        "org_id": current_tenant_org_id.get(),
        "bypass": current_tenant_bypass.get(),
    }


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def apply_tenant_context(
    user: dict[str, Any] | None = None,
) -> None:
    """FastAPI-compatible coroutine that populates the ContextVars
    from the resolved user. In the DI graph we wire it to
    :data:`app.core.security.OptionalUser` so both authenticated and
    unauthenticated requests get a clean context — authenticated
    requests are tenant-pinned, unauthenticated ones fail closed.

    ContextVars are asyncio-task-scoped; each request runs in its own
    task under FastAPI / Starlette, so values never leak between
    concurrent requests or between one request and the next handled
    by the same worker. We therefore do not reset after the request.
    """
    set_tenant_context(user)

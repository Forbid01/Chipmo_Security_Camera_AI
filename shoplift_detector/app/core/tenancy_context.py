"""Per-request tenant context for RLS GUC population.

This is the upstream half of the Layer-2 (Postgres RLS) defense
designed in T02-24 and T1-04. The downstream half — the SQLAlchemy
event hook that writes `SET LOCAL app.current_tenant_id` /
`app.current_org_id` / `app.bypass_tenant` at transaction begin —
lives in `app.db.tenancy_events` and reads from the ContextVars
defined here.

Contract:

- `current_tenant_id` holds the authenticated user's tenant UUID as a
  string. `None` means "no tenant asserted" — the event hook emits
  the fail-closed sentinel so RLS policies match zero rows.
- `current_tenant_org_id` holds the legacy integer organization id.
  Kept in parallel with `current_tenant_id` so pre-UUID code paths
  continue working during rollout.
- `current_tenant_bypass` is `True` only for super-admin paths that
  legitimately need to see every tenant's data.
- ContextVars are thread-safe AND task-safe — an asyncio task sees
  its own value, not another task's, even when multiple requests are
  interleaved on the same event loop.

The FastAPI dependency `apply_tenant_context` is hung on the main API
router so every authenticated request populates the context before
its handler runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

# Sentinels used by the event hook to produce the four possible states
# via ContextVar reads. See `app.db.tenancy_events`.
#
# `current_tenant_id` holds the authenticated user's tenant UUID (as a
# string) and feeds the `app.current_tenant_id` GUC consulted by the
# T1-04 RLS policies. `current_tenant_org_id` is the legacy integer
# organization id — preserved so code and queries that pre-date the
# UUID tenant model keep working during the rollout window.

current_tenant_org_id: ContextVar[int | None] = ContextVar(
    "current_tenant_org_id", default=None
)
current_tenant_id: ContextVar[str | None] = ContextVar(
    "current_tenant_id", default=None
)
current_tenant_bypass: ContextVar[bool] = ContextVar(
    "current_tenant_bypass", default=False
)

# Three-element tuple: (org_token, tenant_token, bypass_token). The
# order is load-bearing for `reset_tenant_context`.
ContextTokens = tuple[Token, Token, Token]


def _coerce_tenant_id(raw: Any) -> str | None:
    """Return a non-empty string or None. Empty string is normalized to
    None so the GUC writer emits the fail-closed sentinel (empty GUC)
    rather than a literal `''` that still reaches the policy."""
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def set_tenant_context(user: dict[str, Any] | None) -> ContextTokens:
    """Populate the ContextVars from a CurrentUser dict.

    Returns the reset Tokens so callers can restore the previous values
    symmetrically. Most call sites should use :func:`tenant_context`
    (a context manager) instead of managing the tokens directly.
    """
    if user is None:
        org_token = current_tenant_org_id.set(None)
        tenant_token = current_tenant_id.set(None)
        bypass_token = current_tenant_bypass.set(False)
        return org_token, tenant_token, bypass_token

    if user.get("role") == "super_admin":
        # Super-admin sessions must not carry a tenant-specific id; the
        # bypass flag governs access instead so we cannot accidentally
        # leak into a specific tenant's rows.
        org_token = current_tenant_org_id.set(None)
        tenant_token = current_tenant_id.set(None)
        bypass_token = current_tenant_bypass.set(True)
        return org_token, tenant_token, bypass_token

    org_id = user.get("org_id")
    # Coerce to int so the SET LOCAL serialization later doesn't have
    # to re-validate. None is a legal value and means "fail closed".
    org_value: int | None = int(org_id) if isinstance(org_id, int) else None
    org_token = current_tenant_org_id.set(org_value)
    tenant_token = current_tenant_id.set(_coerce_tenant_id(user.get("tenant_id")))
    bypass_token = current_tenant_bypass.set(False)
    return org_token, tenant_token, bypass_token


def reset_tenant_context(tokens: ContextTokens) -> None:
    org_token, tenant_token, bypass_token = tokens
    current_tenant_org_id.reset(org_token)
    current_tenant_id.reset(tenant_token)
    current_tenant_bypass.reset(bypass_token)


@contextmanager
def tenant_context(user: dict[str, Any] | None) -> Iterator[None]:
    """Scoped population of the tenancy ContextVars.

    Useful for code paths that run outside a FastAPI request (e.g.
    background workers, scripts) and want to issue DB queries under a
    specific tenant. Pass ``{"role": "super_admin"}`` to run the body
    with RLS bypass — required for system tasks like auto-learning or
    clip retention once ``TENANCY_RLS_ENFORCED`` is on.
    """
    tokens = set_tenant_context(user)
    try:
        yield
    finally:
        reset_tenant_context(tokens)


@contextmanager
def system_bypass() -> Iterator[None]:
    """Run the wrapped block as a system/background task with RLS
    bypass. Required for every background code path that legitimately
    spans tenants (auto-learner, clip retention, camera health
    heartbeat, AI alert dispatcher) once ``TENANCY_RLS_ENFORCED`` is
    on — otherwise their DB sessions would fail closed for lack of a
    tenant id in context.

    Sync and async safe: ContextVars set here are visible to all
    `await` points inside the block and are restored on exit even if
    the block raises. Do NOT use in request handlers — those already
    get the caller's tenant context from the FastAPI dependency.
    """
    with tenant_context({"role": "super_admin"}):
        yield


def snapshot() -> dict[str, Any]:
    """Return the current context as a dict (diagnostic helper)."""
    return {
        "org_id": current_tenant_org_id.get(),
        "tenant_id": current_tenant_id.get(),
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

"""SQLAlchemy `after_begin` event — writes the RLS GUCs per transaction.

Implements §3.4 of the T02-24 RLS spike
(`docs/spikes/postgres-rls-under-asyncpg.md`) plus the T1-04 tenant-id
wiring. On every transaction open (sync or async via AsyncSession),
this hook sets the session-scoped GUCs from the ContextVars owned by
:mod:`shoplift_detector.app.core.tenancy_context`.

GUCs written:

- ``app.current_tenant_id`` — the authenticated user's tenant UUID,
  as a string. Read by the RLS policies installed in migration
  ``20260422_04_enable_tenant_rls``. Empty string when no tenant is in
  context — the policies use ``NULLIF(..., '')::uuid`` which then
  yields NULL and matches no row (fail-closed).
- ``app.current_org_id`` — the legacy integer organization id. Kept in
  parallel so code paths that still key on org_id continue to function
  during the rollout window.
- ``app.bypass_tenant`` — ``'on'`` for super-admin sessions and for
  every session when the feature flag ``TENANCY_RLS_ENFORCED`` is off.
  Policies check this flag before falling through to the tenant-id
  predicate.

Feature flag ``TENANCY_RLS_ENFORCED``:

- ``False`` (current default): every session starts with
  ``app.bypass_tenant='on'``. The RLS policies installed by the
  migration remain in place but never fire, so the app-layer
  ``require_*_access`` guards are the sole enforcement. This is the
  safe rollout state — the migration can land without coordinating a
  code deploy that wires tenant_id into the context.
- ``True`` (prod target): RLS is fully active. Super-admin sessions
  still use ``bypass='on'``; regular sessions pin
  ``app.current_tenant_id`` to the caller's tenant UUID and fail
  closed when the tenant is missing from the context.

Design notes:

- ``SET LOCAL`` is the only SET variant that composes with transaction-
  pooled PgBouncer and with connection pools that reuse connections.
  It scopes to the current transaction, which the hook is guaranteed
  to be inside since it fires from ``after_begin``.
- On non-Postgres dialects (SQLite in unit tests) we skip the SET
  entirely. Tests can still exercise the hook; they just won't see
  the SQL fired at the DB layer.
- The handler is intentionally resilient: any exception during the
  SET is swallowed and logged. A broken GUC writer must NOT take down
  the entire request — the app-level T02-21 guard is already
  authoritative and RLS is defense in depth.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.tenancy_context import (
    current_tenant_bypass,
    current_tenant_id,
    current_tenant_org_id,
)
from sqlalchemy import event, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# GUC names are hard-coded constants because the T1-04 and T02-26 RLS
# policies reference them literally. Changing one side without the
# other would silently disable enforcement.
GUC_ORG_ID = "app.current_org_id"
GUC_TENANT_ID = "app.current_tenant_id"
GUC_BYPASS = "app.bypass_tenant"

# Sentinel for "no tenant in context — deny by default".
FAIL_CLOSED_ORG_ID = "-1"
# Empty string so the policy's NULLIF(..., '')::uuid cast yields NULL
# and the OR clause falls through to a no-match (fail-closed).
FAIL_CLOSED_TENANT_ID = ""


def _set_bypass_all(connection: Any) -> None:
    """Write the 'RLS disabled' GUC set — bypass on, sentinels elsewhere.

    Used both by the super-admin branch and by the legacy-mode branch
    when ``TENANCY_RLS_ENFORCED`` is off.
    """
    connection.execute(text(f"SET LOCAL {GUC_BYPASS} = 'on'"))
    # When bypass is on, tenant_id / org_id are irrelevant — policies
    # ignore them. Still set them to known sentinels so a policy that
    # forgets the bypass branch (or a future debugging query) does not
    # accidentally match a real tenant.
    connection.execute(
        text(f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'")
    )
    connection.execute(
        text(f"SET LOCAL {GUC_TENANT_ID} = '{FAIL_CLOSED_TENANT_ID}'")
    )


def apply_tenant_gucs(connection: Any) -> None:
    """Issue the SET LOCAL statements against ``connection``.

    Exposed separately so it can be unit-tested without going through
    SQLAlchemy's event dispatch. Callers are the hook below and the
    regression tests.
    """
    # Skip silently on non-Postgres dialects. Tests use SQLite, which
    # rejects the app.* GUCs. The hook is still registered; the SQL
    # just doesn't run.
    dialect_name = getattr(getattr(connection, "dialect", None), "name", "")
    if dialect_name and dialect_name != "postgresql":
        return

    org_id = current_tenant_org_id.get()
    tenant_id = current_tenant_id.get()
    bypass = current_tenant_bypass.get()

    try:
        # Legacy mode: RLS policies exist but must not block anything.
        # Every session gets bypass='on' so the app-layer guard is the
        # sole enforcement. This is the default until prod flips the
        # flag.
        if not settings.TENANCY_RLS_ENFORCED:
            _set_bypass_all(connection)
            return

        # Enforced mode: super-admin still bypasses, everyone else
        # must carry a tenant_id or fail closed.
        if bypass:
            _set_bypass_all(connection)
            return

        connection.execute(text(f"SET LOCAL {GUC_BYPASS} = 'off'"))

        # Legacy org_id alongside — some repository code still filters
        # on it; keep the parallel write until those paths migrate.
        if org_id is None:
            connection.execute(
                text(f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'")
            )
        else:
            connection.execute(
                text(f"SET LOCAL {GUC_ORG_ID} = :v"),
                {"v": str(int(org_id))},
            )

        # The load-bearing write for T1-04 RLS. NULLIF in the policy
        # turns the empty sentinel back into NULL, which then fails to
        # match any UUID and the OR clause denies the row.
        if tenant_id is None:
            connection.execute(
                text(f"SET LOCAL {GUC_TENANT_ID} = '{FAIL_CLOSED_TENANT_ID}'")
            )
        else:
            connection.execute(
                text(f"SET LOCAL {GUC_TENANT_ID} = :v"),
                {"v": str(tenant_id)},
            )
    except Exception as exc:
        # RLS is defense-in-depth; the app-layer guard (T02-21) is
        # already authoritative. Log loudly and let the request
        # proceed so a broken hook doesn't cause a site-wide outage.
        logger.error(
            "tenancy GUC setter failed; proceeding without RLS context: %s",
            exc,
        )


_REGISTERED = False


def install_tenancy_event_hook() -> None:
    """Attach the `after_begin` listener once per process.

    Safe to call multiple times; idempotent. Called automatically on
    import of :mod:`app.db.session` so every DB usage in the app
    inherits the hook without needing to know it exists.
    """
    global _REGISTERED
    if _REGISTERED:
        return

    @event.listens_for(Session, "after_begin")
    def _after_begin(session, transaction, connection):  # noqa: ARG001
        apply_tenant_gucs(connection)

    _REGISTERED = True


def _reset_for_tests() -> None:
    """Pytest helper — clears the idempotency flag so a test can
    re-install the hook against a fresh registry.
    """
    global _REGISTERED
    _REGISTERED = False

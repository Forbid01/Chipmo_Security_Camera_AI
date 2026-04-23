"""SQLAlchemy `after_begin` event — writes the RLS GUCs per transaction.

Implements §3.4 of the T02-24 RLS spike
(`docs/spikes/postgres-rls-under-asyncpg.md`). On every transaction
open (sync or async via AsyncSession), this hook sets two session-
scoped GUCs from the ContextVars owned by
:mod:`shoplift_detector.app.core.tenancy_context`:

- ``app.current_org_id`` — the authenticated user's organization id,
  coerced to a string. When no tenant is in context, we fail closed
  to ``'-1'`` so RLS policies (T02-26) match zero rows.
- ``app.bypass_tenant`` — ``'on'`` for super-admin sessions,
  ``'off'`` otherwise. Policies check this flag before falling through
  to the org-id predicate.

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

from app.core.tenancy_context import (
    current_tenant_bypass,
    current_tenant_org_id,
)
from sqlalchemy import event, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# GUC names are hard-coded constants because the T02-26 RLS policies
# will reference them literally. Changing one side without the other
# would silently disable enforcement.
GUC_ORG_ID = "app.current_org_id"
GUC_BYPASS = "app.bypass_tenant"

# Sentinel for "no tenant in context — deny by default".
FAIL_CLOSED_ORG_ID = "-1"


def apply_tenant_gucs(connection: Any) -> None:
    """Issue the two SET LOCAL statements against ``connection``.

    Exposed separately so it can be unit-tested without going through
    SQLAlchemy's event dispatch. Callers are the hook below and the
    regression tests.
    """
    org_id = current_tenant_org_id.get()
    bypass = current_tenant_bypass.get()

    # Skip silently on non-Postgres dialects. Tests use SQLite, which
    # rejects the app.* GUCs. The hook is still registered; the SQL
    # just doesn't run.
    dialect_name = getattr(getattr(connection, "dialect", None), "name", "")
    if dialect_name and dialect_name != "postgresql":
        return

    try:
        if bypass:
            connection.execute(text(f"SET LOCAL {GUC_BYPASS} = 'on'"))
            # When bypass is on, org_id is irrelevant — policies ignore
            # it. Still set it to a known sentinel so a policy that
            # forgets the bypass branch (or a future debugging query)
            # does not accidentally match a real tenant.
            connection.execute(
                text(f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'")
            )
            return

        connection.execute(text(f"SET LOCAL {GUC_BYPASS} = 'off'"))

        if org_id is None:
            # Fail closed: unauthenticated request, system task, or
            # misconfigured caller. RLS policies see `-1`, which is
            # not a valid organization id, and therefore match no row.
            connection.execute(
                text(f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'")
            )
            return

        connection.execute(
            text(f"SET LOCAL {GUC_ORG_ID} = :v"), {"v": str(int(org_id))}
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

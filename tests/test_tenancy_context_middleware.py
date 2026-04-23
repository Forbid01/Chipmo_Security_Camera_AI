"""Tests for T02-25 — RLS GUC setter middleware.

Split into four concerns:

1. `app.core.tenancy_context` — ContextVar semantics, super-admin
   bypass, int coercion, reset roundtrip.
2. `app.db.tenancy_events.apply_tenant_gucs` — correct SQL under
   each of the three states (authenticated tenant / super-admin
   bypass / fail-closed), dialect skip on SQLite, exception
   swallow on DB failure.
3. `install_tenancy_event_hook` — idempotent; listener actually
   registered on `Session`.
4. `apply_tenant_context` FastAPI dependency — populates ContextVar
   from the resolved user, respects the super-admin branch.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.core.tenancy_context import (
    apply_tenant_context,
    current_tenant_bypass,
    current_tenant_org_id,
    reset_tenant_context,
    set_tenant_context,
    snapshot,
    tenant_context,
)
from app.db import tenancy_events
from app.db.tenancy_events import (
    FAIL_CLOSED_ORG_ID,
    GUC_BYPASS,
    GUC_ORG_ID,
    apply_tenant_gucs,
    install_tenancy_event_hook,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeConnection:
    """Collects SET LOCAL statements without talking to any DB."""

    def __init__(self, dialect_name: str = "postgresql"):
        self.dialect = MagicMock()
        self.dialect.name = dialect_name
        self.executed: list[tuple[str, dict | None]] = []

    def execute(self, query, params=None):
        self.executed.append((str(query), dict(params) if params else None))


@pytest.fixture(autouse=True)
def _clear_context_between_tests():
    org_token = current_tenant_org_id.set(None)
    bypass_token = current_tenant_bypass.set(False)
    yield
    current_tenant_org_id.reset(org_token)
    current_tenant_bypass.reset(bypass_token)


# ---------------------------------------------------------------------------
# ContextVar semantics
# ---------------------------------------------------------------------------

def test_default_context_is_fail_closed_and_not_bypass():
    # Module default — no one set anything.
    assert current_tenant_org_id.get() is None
    assert current_tenant_bypass.get() is False


def test_set_tenant_context_none_user_preserves_fail_closed():
    tokens = set_tenant_context(None)
    assert current_tenant_org_id.get() is None
    assert current_tenant_bypass.get() is False
    reset_tenant_context(tokens)


def test_set_tenant_context_regular_user_pins_org_id():
    tokens = set_tenant_context({"role": "admin", "org_id": 42})
    assert current_tenant_org_id.get() == 42
    assert current_tenant_bypass.get() is False
    reset_tenant_context(tokens)


def test_set_tenant_context_super_admin_flips_bypass_not_org():
    tokens = set_tenant_context({"role": "super_admin", "org_id": 99})
    # Super admin sessions must not carry a tenant-specific org_id; the
    # bypass flag governs access instead so we cannot accidentally leak
    # into a specific tenant's rows.
    assert current_tenant_org_id.get() is None
    assert current_tenant_bypass.get() is True
    reset_tenant_context(tokens)


def test_set_tenant_context_coerces_str_org_id_to_none():
    # A JWT that somehow stored org_id as a string must not silently
    # land in the ContextVar unvalidated — the GUC setter requires
    # int serialization.
    tokens = set_tenant_context({"role": "admin", "org_id": "100"})
    assert current_tenant_org_id.get() is None
    reset_tenant_context(tokens)


def test_tenant_context_manager_restores_previous_values():
    set_tenant_context({"role": "admin", "org_id": 7})
    before = snapshot()

    with tenant_context({"role": "super_admin"}):
        assert current_tenant_bypass.get() is True

    after = snapshot()
    assert after == before


# ---------------------------------------------------------------------------
# apply_tenant_gucs — per-state SQL
# ---------------------------------------------------------------------------

def test_apply_gucs_regular_tenant_emits_org_id_and_off_bypass():
    set_tenant_context({"role": "admin", "org_id": 42})
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'off'" in q for q in queries)
    assert any(f"SET LOCAL {GUC_ORG_ID} = :v" in q for q in queries)
    # The int must have been coerced to a string for the bind param.
    assert conn.executed[-1][1] == {"v": "42"}


def test_apply_gucs_super_admin_emits_on_bypass_and_sentinel_org():
    set_tenant_context({"role": "super_admin"})
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'on'" in q for q in queries)
    # Org id still written to the fail-closed sentinel so a forgotten
    # policy branch cannot match a real tenant.
    assert any(
        f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'" in q for q in queries
    )


def test_apply_gucs_fail_closed_when_no_context():
    # ContextVars are at their defaults (autouse fixture reset them).
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'off'" in q for q in queries)
    assert any(
        f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'" in q for q in queries
    )


def test_apply_gucs_skips_on_sqlite_dialect():
    # SQLite doesn't know about app.* GUCs; tests run against it.
    # The hook must be a no-op there.
    set_tenant_context({"role": "admin", "org_id": 42})
    conn = _FakeConnection(dialect_name="sqlite")

    apply_tenant_gucs(conn)

    assert conn.executed == []


def test_apply_gucs_swallows_db_errors_without_raising():
    set_tenant_context({"role": "admin", "org_id": 42})

    class _Boom(_FakeConnection):
        def execute(self, query, params=None):  # noqa: ARG002
            raise RuntimeError("connection gone")

    # Must not raise — RLS is defense-in-depth, not a hard gate.
    apply_tenant_gucs(_Boom())


# ---------------------------------------------------------------------------
# Hook registration — idempotent install
# ---------------------------------------------------------------------------

def test_install_tenancy_event_hook_is_idempotent():
    # Importing `app.db.session` already triggers a single install.
    # Calling again must not double-register.
    install_tenancy_event_hook()
    install_tenancy_event_hook()
    install_tenancy_event_hook()

    # The idempotency flag is what guards re-install.
    assert tenancy_events._REGISTERED is True


def test_hook_fires_on_real_session_begin(monkeypatch):
    """End-to-end: opening a real SQLAlchemy Session transaction must
    dispatch into `apply_tenant_gucs`. We spy the helper and kick a
    session through a transaction to confirm the wiring holds.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Replace apply_tenant_gucs with a spy so we can confirm the hook
    # reached it without needing a Postgres backend.
    calls: list[object] = []

    def _spy(conn):
        calls.append(conn)

    monkeypatch.setattr(tenancy_events, "apply_tenant_gucs", _spy)

    # Make sure the hook is installed (module import already did it,
    # but call again idempotently to be explicit in the test).
    install_tenancy_event_hook()

    engine = create_engine("sqlite:///:memory:")
    Sess = sessionmaker(bind=engine)
    with Sess() as s:
        s.begin()
        s.execute(__import__("sqlalchemy").text("SELECT 1"))
        s.commit()

    assert calls, "after_begin handler never fired"


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_tenant_context_dep_pins_tenant_for_admin():
    await apply_tenant_context({"role": "admin", "org_id": 42})
    assert current_tenant_org_id.get() == 42
    assert current_tenant_bypass.get() is False


@pytest.mark.asyncio
async def test_apply_tenant_context_dep_flips_bypass_for_super_admin():
    await apply_tenant_context({"role": "super_admin"})
    assert current_tenant_org_id.get() is None
    assert current_tenant_bypass.get() is True


@pytest.mark.asyncio
async def test_apply_tenant_context_dep_none_user_is_fail_closed():
    await apply_tenant_context(None)
    assert current_tenant_org_id.get() is None
    assert current_tenant_bypass.get() is False


@pytest.mark.asyncio
async def test_apply_tenant_context_dep_end_to_end_through_api_router(client):
    """Hitting any /api/v1/* route must have populated the ContextVar
    for the duration of that request. We verify indirectly by calling
    the `/api/v1/metrics` endpoint which does not require auth, so it
    reaches the router-level dep without blocking on auth first.
    """
    # The ContextVar state from *this* task is independent of the
    # server task, so we can't read it directly. Instead we assert
    # the call succeeds, which proves the dependency chain resolves.
    response = await client.get("/api/v1/metrics")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Wire-level integration — main app exposes the dep on api_router
# ---------------------------------------------------------------------------

def test_api_router_has_tenant_context_dependency():
    from shoplift_detector.main import app

    api_v1 = [r for r in app.router.routes if getattr(r, "path", "").startswith("/api/v1")]
    assert api_v1, "api_router not mounted"

    # At least one route's dependencies list references the tenant
    # populator. We look for its qualname to avoid module-identity
    # issues between `app.*` and `shoplift_detector.app.*`.
    for route in api_v1:
        deps = getattr(route, "dependant", None)
        if deps is None:
            continue
        for dep in getattr(deps, "dependencies", []):
            call = getattr(dep, "call", None)
            if call is None:
                continue
            if "tenant_context" in getattr(call, "__qualname__", "").lower() or \
               "populate_tenant_context" in getattr(call, "__qualname__", ""):
                return
    pytest.fail("No /api/v1 route inherits the tenant-context dependency")

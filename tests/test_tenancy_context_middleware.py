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
    current_tenant_id,
    current_tenant_org_id,
    reset_tenant_context,
    set_tenant_context,
    snapshot,
    system_bypass,
    tenant_context,
)
from app.db import tenancy_events
from app.db.tenancy_events import (
    FAIL_CLOSED_ORG_ID,
    FAIL_CLOSED_TENANT_ID,
    GUC_BYPASS,
    GUC_ORG_ID,
    GUC_TENANT_ID,
    apply_tenant_gucs,
    install_tenancy_event_hook,
)


@pytest.fixture
def rls_enforced(monkeypatch):
    """Flip TENANCY_RLS_ENFORCED on for tests that exercise the
    enforced code path. Default is off so legacy behavior (bypass='on')
    is the fixture-less baseline."""
    monkeypatch.setattr(tenancy_events.settings, "TENANCY_RLS_ENFORCED", True)

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
    tenant_token = current_tenant_id.set(None)
    bypass_token = current_tenant_bypass.set(False)
    yield
    current_tenant_org_id.reset(org_token)
    current_tenant_id.reset(tenant_token)
    current_tenant_bypass.reset(bypass_token)


# ---------------------------------------------------------------------------
# ContextVar semantics
# ---------------------------------------------------------------------------

def test_default_context_is_fail_closed_and_not_bypass():
    # Module default — no one set anything.
    assert current_tenant_org_id.get() is None
    assert current_tenant_id.get() is None
    assert current_tenant_bypass.get() is False


def test_set_tenant_context_none_user_preserves_fail_closed():
    tokens = set_tenant_context(None)
    assert current_tenant_org_id.get() is None
    assert current_tenant_id.get() is None
    assert current_tenant_bypass.get() is False
    reset_tenant_context(tokens)


def test_set_tenant_context_regular_user_pins_org_id_and_tenant_id():
    tenant_uuid = "11111111-1111-1111-1111-111111111111"
    tokens = set_tenant_context(
        {"role": "admin", "org_id": 42, "tenant_id": tenant_uuid}
    )
    assert current_tenant_org_id.get() == 42
    assert current_tenant_id.get() == tenant_uuid
    assert current_tenant_bypass.get() is False
    reset_tenant_context(tokens)


def test_set_tenant_context_super_admin_flips_bypass_not_org():
    tokens = set_tenant_context(
        {"role": "super_admin", "org_id": 99,
         "tenant_id": "99999999-9999-9999-9999-999999999999"}
    )
    # Super admin sessions must not carry a tenant-specific org_id or
    # tenant_id; the bypass flag governs access instead so we cannot
    # accidentally leak into a specific tenant's rows.
    assert current_tenant_org_id.get() is None
    assert current_tenant_id.get() is None
    assert current_tenant_bypass.get() is True
    reset_tenant_context(tokens)


def test_set_tenant_context_coerces_str_org_id_to_none():
    # A JWT that somehow stored org_id as a string must not silently
    # land in the ContextVar unvalidated — the GUC setter requires
    # int serialization.
    tokens = set_tenant_context({"role": "admin", "org_id": "100"})
    assert current_tenant_org_id.get() is None
    reset_tenant_context(tokens)


def test_set_tenant_context_normalizes_empty_tenant_id_to_none():
    # A blank claim must not surface as a literal empty string in the
    # ContextVar — that would bypass the fail-closed sentinel logic in
    # the GUC writer.
    tokens = set_tenant_context({"role": "admin", "org_id": 1, "tenant_id": ""})
    assert current_tenant_id.get() is None
    reset_tenant_context(tokens)


def test_tenant_context_manager_restores_previous_values():
    set_tenant_context({"role": "admin", "org_id": 7})
    before = snapshot()

    with tenant_context({"role": "super_admin"}):
        assert current_tenant_bypass.get() is True

    after = snapshot()
    assert after == before


# ---------------------------------------------------------------------------
# system_bypass — background task RLS bypass
# ---------------------------------------------------------------------------

def test_system_bypass_flips_bypass_on_for_wrapped_block():
    # Background task default — no user in context.
    assert current_tenant_bypass.get() is False

    with system_bypass():
        assert current_tenant_bypass.get() is True
        assert current_tenant_id.get() is None
        assert current_tenant_org_id.get() is None


def test_system_bypass_restores_previous_state_on_exit():
    # Simulate a request context already pinned to a tenant.
    set_tenant_context(
        {"role": "admin", "org_id": 5,
         "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
    )
    before = snapshot()

    with system_bypass():
        assert current_tenant_bypass.get() is True

    after = snapshot()
    assert after == before


def test_system_bypass_restores_state_even_when_block_raises():
    set_tenant_context({"role": "admin", "org_id": 5,
                        "tenant_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"})
    before = snapshot()

    with pytest.raises(RuntimeError):
        with system_bypass():
            raise RuntimeError("boom")

    after = snapshot()
    assert after == before


@pytest.mark.asyncio
async def test_system_bypass_persists_across_await(rls_enforced):
    # Background tasks do `with system_bypass(): async with AsyncSessionLocal():`.
    # The GUC hook reads ContextVars after the await at transaction
    # begin, so the bypass state must survive across await boundaries.
    conn = _FakeConnection()

    async def _op():
        apply_tenant_gucs(conn)

    with system_bypass():
        await _op()

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'on'" in q for q in queries)


# ---------------------------------------------------------------------------
# apply_tenant_gucs — per-state SQL (legacy/bypass mode, flag OFF)
# ---------------------------------------------------------------------------

def test_apply_gucs_flag_off_bypasses_every_session_regardless_of_role():
    # TENANCY_RLS_ENFORCED default is False — every session gets
    # bypass='on' so RLS policies are effectively disabled and the
    # app-layer guard remains the sole enforcement.
    set_tenant_context({"role": "admin", "org_id": 42,
                        "tenant_id": "11111111-1111-1111-1111-111111111111"})
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'on'" in q for q in queries)
    assert any(
        f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'" in q for q in queries
    )
    # Tenant id must also land at the fail-closed sentinel so a policy
    # that ignores the bypass flag still sees no match.
    assert any(
        f"SET LOCAL {GUC_TENANT_ID} = '{FAIL_CLOSED_TENANT_ID}'" in q
        for q in queries
    )


def test_apply_gucs_flag_off_still_writes_sentinel_without_context():
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    # Even without any user in context, legacy mode yields bypass='on'.
    assert any(f"SET LOCAL {GUC_BYPASS} = 'on'" in q for q in queries)


# ---------------------------------------------------------------------------
# apply_tenant_gucs — enforced mode (flag ON)
# ---------------------------------------------------------------------------

def test_apply_gucs_enforced_regular_tenant_pins_tenant_id(rls_enforced):
    tenant_uuid = "11111111-1111-1111-1111-111111111111"
    set_tenant_context({"role": "admin", "org_id": 42, "tenant_id": tenant_uuid})
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'off'" in q for q in queries)
    assert any(f"SET LOCAL {GUC_ORG_ID} = :v" in q for q in queries)
    assert any(f"SET LOCAL {GUC_TENANT_ID} = :v" in q for q in queries)

    params = [p for _, p in conn.executed if p]
    assert {"v": "42"} in params
    assert {"v": tenant_uuid} in params


def test_apply_gucs_enforced_super_admin_still_bypasses(rls_enforced):
    set_tenant_context({"role": "super_admin"})
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'on'" in q for q in queries)
    assert any(
        f"SET LOCAL {GUC_TENANT_ID} = '{FAIL_CLOSED_TENANT_ID}'" in q
        for q in queries
    )


def test_apply_gucs_enforced_missing_tenant_fails_closed(rls_enforced):
    # A JWT issued before the tenant_id claim landed — user dict has
    # role/org but no tenant_id. RLS must block everything rather than
    # silently widen visibility.
    set_tenant_context({"role": "admin", "org_id": 42})
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'off'" in q for q in queries)
    assert any(
        f"SET LOCAL {GUC_TENANT_ID} = '{FAIL_CLOSED_TENANT_ID}'" in q
        for q in queries
    )


def test_apply_gucs_enforced_no_user_fails_closed(rls_enforced):
    # Unauthenticated request hitting a router that resolves an
    # OptionalUser=None. Enforced mode denies by default.
    conn = _FakeConnection()

    apply_tenant_gucs(conn)

    queries = [q for q, _ in conn.executed]
    assert any(f"SET LOCAL {GUC_BYPASS} = 'off'" in q for q in queries)
    assert any(
        f"SET LOCAL {GUC_TENANT_ID} = '{FAIL_CLOSED_TENANT_ID}'" in q
        for q in queries
    )
    assert any(
        f"SET LOCAL {GUC_ORG_ID} = '{FAIL_CLOSED_ORG_ID}'" in q for q in queries
    )


def test_apply_gucs_skips_on_sqlite_dialect(rls_enforced):
    # SQLite doesn't know about app.* GUCs; tests run against it.
    # The hook must be a no-op there — even with the flag enforced.
    set_tenant_context({"role": "admin", "org_id": 42,
                        "tenant_id": "22222222-2222-2222-2222-222222222222"})
    conn = _FakeConnection(dialect_name="sqlite")

    apply_tenant_gucs(conn)

    assert conn.executed == []


def test_apply_gucs_swallows_db_errors_without_raising(rls_enforced):
    set_tenant_context({"role": "admin", "org_id": 42,
                        "tenant_id": "33333333-3333-3333-3333-333333333333"})

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

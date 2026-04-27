"""Live-Postgres integration test for T1-04 RLS enforcement.

Most of the tenancy test suite runs against SQLite where RLS is a
no-op, so the hook is verified by inspecting the SQL it would have
emitted. This file exercises the other half: given a real Postgres
server, a policy template mirroring migration 20260422_04, and the
production ``apply_tenant_gucs`` writer, does cross-tenant SELECT /
INSERT actually get blocked?

The test is opt-in — set ``RLS_TEST_DATABASE_URL`` to a Postgres DSN
(e.g. ``postgresql://postgres:postgres@localhost:5432/postgres``) and
run pytest. Without the env var the whole module is skipped so CI
environments without Postgres aren't broken.

The fixture installs the RLS scaffolding against a throwaway table
named ``_rls_probe`` so the test cannot collide with real data. The
table is dropped on teardown even when assertions fail.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.integration

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.tenancy_context import (  # noqa: E402
    current_tenant_bypass,
    current_tenant_id,
    current_tenant_org_id,
    set_tenant_context,
)
from app.db import tenancy_events  # noqa: E402
from app.db.tenancy_events import install_tenancy_event_hook  # noqa: E402


_DSN = os.environ.get("RLS_TEST_DATABASE_URL")

if not _DSN:
    pytest.skip(
        "Set RLS_TEST_DATABASE_URL to a Postgres DSN to run RLS integration tests",
        allow_module_level=True,
    )


# Policy body is the same shape as production (migration 20260422_04):
# super-admin bypass short-circuits via the GUC flag, otherwise the
# row's tenant_id must match the session GUC.
_POLICY_BODY = """
    COALESCE(current_setting('app.bypass_tenant', true), 'off') = 'on'
    OR tenant_id = NULLIF(
        current_setting('app.current_tenant_id', true), ''
    )::uuid
"""


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(_DSN, future=True)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS _rls_probe"))
        conn.execute(
            text(
                """
                CREATE TABLE _rls_probe (
                    id SERIAL PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE _rls_probe ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE _rls_probe FORCE ROW LEVEL SECURITY"))
        conn.execute(text("DROP POLICY IF EXISTS _rls_probe_isolation ON _rls_probe"))
        conn.execute(
            text(
                f"""
                CREATE POLICY _rls_probe_isolation ON _rls_probe
                    AS PERMISSIVE
                    FOR ALL
                    TO PUBLIC
                    USING ({_POLICY_BODY})
                    WITH CHECK ({_POLICY_BODY})
                """
            )
        )
    yield eng
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS _rls_probe"))
    eng.dispose()


TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def _isolated_context():
    """Reset ContextVars between tests so one test's set_tenant_context
    call cannot leak into the next — pytest keeps the process alive
    across tests and ContextVars are not auto-reset otherwise."""
    org_token = current_tenant_org_id.set(None)
    tenant_token = current_tenant_id.set(None)
    bypass_token = current_tenant_bypass.set(False)
    yield
    current_tenant_org_id.reset(org_token)
    current_tenant_id.reset(tenant_token)
    current_tenant_bypass.reset(bypass_token)


@pytest.fixture
def seeded(engine, monkeypatch):
    """Each test starts with two rows — one per tenant. Seeded with
    bypass='on' so the INSERTs clear the WITH CHECK predicate; the
    test itself then flips context and asserts isolation."""
    monkeypatch.setattr(tenancy_events.settings, "TENANCY_RLS_ENFORCED", True)
    install_tenancy_event_hook()

    # Seed as super-admin (bypass='on') so both rows land regardless
    # of policy state. The autouse fixture will wipe this context at
    # teardown so it doesn't leak into the next test.
    set_tenant_context({"role": "super_admin"})
    Sess = sessionmaker(bind=engine, future=True)
    with Sess.begin() as s:
        s.execute(text("TRUNCATE _rls_probe RESTART IDENTITY"))
        s.execute(
            text("INSERT INTO _rls_probe (tenant_id, payload) VALUES (:t, :p)"),
            [
                {"t": str(TENANT_A), "p": "A-row"},
                {"t": str(TENANT_B), "p": "B-row"},
            ],
        )
    yield Sess


def _select_all(Sess) -> list[tuple[str, str]]:
    with Sess.begin() as s:
        rows = s.execute(
            text("SELECT tenant_id::text, payload FROM _rls_probe ORDER BY payload")
        ).all()
    return [(r[0], r[1]) for r in rows]


def test_tenant_a_sees_only_its_own_row(seeded):
    set_tenant_context(
        {"role": "admin", "org_id": 1, "tenant_id": str(TENANT_A)}
    )
    rows = _select_all(seeded)
    assert rows == [(str(TENANT_A), "A-row")]


def test_tenant_b_sees_only_its_own_row(seeded):
    set_tenant_context(
        {"role": "admin", "org_id": 2, "tenant_id": str(TENANT_B)}
    )
    rows = _select_all(seeded)
    assert rows == [(str(TENANT_B), "B-row")]


def test_super_admin_bypass_sees_every_row(seeded):
    set_tenant_context({"role": "super_admin"})
    rows = _select_all(seeded)
    assert len(rows) == 2
    payloads = {r[1] for r in rows}
    assert payloads == {"A-row", "B-row"}


def test_missing_tenant_id_fails_closed(seeded):
    # A JWT without a tenant_id claim must not return anything — the
    # policy's NULLIF('')::uuid yields NULL and the row predicate
    # evaluates to NULL, which RLS treats as reject.
    set_tenant_context({"role": "admin", "org_id": 1})
    rows = _select_all(seeded)
    assert rows == []


def test_unauthenticated_session_fails_closed(seeded):
    set_tenant_context(None)
    rows = _select_all(seeded)
    assert rows == []


def test_cross_tenant_insert_is_rejected_by_with_check(seeded):
    set_tenant_context(
        {"role": "admin", "org_id": 1, "tenant_id": str(TENANT_A)}
    )
    Sess = seeded
    import sqlalchemy as sa

    with pytest.raises(sa.exc.DBAPIError):
        with Sess.begin() as s:
            s.execute(
                text(
                    "INSERT INTO _rls_probe (tenant_id, payload) "
                    "VALUES (:t, :p)"
                ),
                {"t": str(TENANT_B), "p": "smuggled"},
            )


def test_flag_off_restores_bypass_and_tenant_a_sees_b(seeded, monkeypatch):
    # When TENANCY_RLS_ENFORCED flips back to False (rollback scenario),
    # the hook writes bypass='on' universally — Layer 1 remains the
    # sole guard. Cross-tenant visibility must therefore come back for
    # the raw DB layer even if Layer 1 would still block.
    monkeypatch.setattr(tenancy_events.settings, "TENANCY_RLS_ENFORCED", False)
    set_tenant_context(
        {"role": "admin", "org_id": 1, "tenant_id": str(TENANT_A)}
    )
    rows = _select_all(seeded)
    payloads = {r[1] for r in rows}
    assert payloads == {"A-row", "B-row"}

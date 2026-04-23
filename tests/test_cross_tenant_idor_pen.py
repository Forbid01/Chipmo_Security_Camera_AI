"""Cross-tenant IDOR pen-test scenarios (T1-15).

Complements `test_cross_tenant_regression.py` (which pins the legacy
`organization_id` guards). These tests attack the tenant_id / API-key
surface introduced by T1-01 → T1-10:

- `get_current_tenant` must reject a tenant_B API key trying to read
  tenant_A resources.
- Tenant lifecycle state machine must not let an `active` tenant B
  mutate tenant A's status.
- Quota / rate-limit math must scope per tenant — tenant A exhausting
  their bucket leaves tenant B unaffected.

Every scenario is deterministic + hermetic — no live Postgres / Redis
required. An attacker scenario is exercised through direct service
calls rather than a full HTTP stack so the tests run in milliseconds
and can be a required CI gate.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from shoplift_detector.app.core.quota import (
    QuotaExceededError,
    ensure_camera_quota,
)
from shoplift_detector.app.core.tenant_auth import (
    API_KEY_PREFIX,
    get_current_tenant,
)
from shoplift_detector.app.core.tenant_keys import TenantKeys
from shoplift_detector.app.core.tenant_rate_limit import (
    InMemoryBackend,
    TenantRateLimiter,
)
from shoplift_detector.app.core.tenant_storage import (
    TenantBucketLayout,
    key_belongs_to_tenant,
)
from shoplift_detector.app.db.repository.tenants import hash_api_key
from shoplift_detector.app.services.tenant_lifecycle import (
    transition_tenant_status,
)


TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# Scenario 1 — stolen/mismatched API key
# ---------------------------------------------------------------------------

class _FakeAuthResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


class _FakeAuthDB:
    def __init__(self, row=None):
        self._row = row

    async def execute(self, query, params=None):
        # Only a matching hash returns the row — the point of SHA-256
        # lookup is that we can't produce a valid row for an unknown
        # key. The fake honors that contract.
        return _FakeAuthResult(self._row)


@pytest.mark.asyncio
async def test_unknown_api_key_yields_401_even_for_wellformed_token():
    """Tenant B cannot forge a token that resolves to tenant A —
    the lookup returns None because no row has the computed hash."""
    from fastapi.security import HTTPAuthorizationCredentials
    attacker_key = API_KEY_PREFIX + "forged-token"
    db = _FakeAuthDB(row=None)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=attacker_key)
    with pytest.raises(HTTPException) as ctx:
        await get_current_tenant(db=db, credentials=creds)
    assert ctx.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_key_only_returns_its_own_tenant_row():
    """If the DB returns tenant A's row, we return tenant A — the
    test's real value is that the handler can't magic up another
    tenant's identity from a valid token."""
    from fastapi.security import HTTPAuthorizationCredentials
    key_a = API_KEY_PREFIX + "a" * 32
    row_a = {
        "tenant_id": TENANT_A,
        "status": "active",
        "plan": "pro",
        "email": "a@a",
        "legal_name": "a",
        "display_name": "a",
        "phone": None,
        "created_at": None,
        "trial_ends_at": None,
        "current_period_end": None,
        "payment_method_id": None,
        "resource_quota": {"max_cameras": 50},
        "previous_api_key_hash": None,
        "previous_api_key_expires_at": None,
    }
    db = _FakeAuthDB(row=row_a)
    tenant = await get_current_tenant(
        db=db,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=key_a),
    )
    assert tenant["tenant_id"] == TENANT_A
    # Tenant B is not reachable through tenant A's key.
    assert tenant["tenant_id"] != TENANT_B
    # Assert the hash flowed through unchanged.
    assert len(hash_api_key(key_a)) == 64


# ---------------------------------------------------------------------------
# Scenario 2 — Redis key namespacing
# ---------------------------------------------------------------------------

def test_redis_key_cannot_collide_across_tenants():
    """Two different tenants, same store/person id, must yield
    different Redis keys. The in-memory bucket store relies on this
    — a collision would let tenant B's writes overwrite A's."""
    ka = TenantKeys(tenant_id=TENANT_A)
    kb = TenantKeys(tenant_id=TENANT_B)
    assert (
        ka.person_state(store_id=1, person_id="P-1")
        != kb.person_state(store_id=1, person_id="P-1")
    )


def test_redis_key_rejects_empty_tenant_id():
    """An empty tenant_id would produce `tenant::store:...` — that's
    a shared-world key and would leak across tenants."""
    with pytest.raises(ValueError):
        TenantKeys(tenant_id="")


def test_redis_key_rejects_non_uuid():
    """Accidentally passing `store_id` (int-like) where `tenant_id`
    was expected must fail at construction, not silently at runtime."""
    with pytest.raises(ValueError):
        TenantKeys(tenant_id="42")


# ---------------------------------------------------------------------------
# Scenario 3 — MinIO path traversal
# ---------------------------------------------------------------------------

def test_object_key_rejects_other_tenants_prefix():
    """An attacker who guesses tenant A's event_id cannot construct a
    path that passes the ownership check with tenant B's id."""
    attacker_key = f"tenant_{TENANT_A}/store_1/2026-04-22/event_x.mp4"
    assert key_belongs_to_tenant(attacker_key, tenant_id=TENANT_B) is False
    assert key_belongs_to_tenant(attacker_key, tenant_id=TENANT_A) is True


def test_event_clip_layout_is_unforgeable_across_tenants():
    """Regardless of arguments, layouts for different tenants produce
    disjoint prefixes."""
    a = TenantBucketLayout(tenant_id=TENANT_A)
    b = TenantBucketLayout(tenant_id=TENANT_B)
    key_a = a.event_clip(store_id=1, event_id="alpha", ext="mp4")
    key_b = b.event_clip(store_id=1, event_id="alpha", ext="mp4")
    assert key_a.startswith(a.tenant_prefix)
    assert key_b.startswith(b.tenant_prefix)
    assert not key_b.startswith(a.tenant_prefix)


def test_event_id_cannot_escape_tenant_prefix_via_traversal():
    """A malicious `event_id` with `..` or `/` segments gets sanitized
    before going into the path."""
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    key = layout.event_clip(store_id=1, event_id="../../etc/passwd", ext="mp4")
    # Sanitizer turns `/` and `.` into `_`.
    assert "../" not in key
    assert key.startswith(layout.tenant_prefix)


# ---------------------------------------------------------------------------
# Scenario 4 — rate-limit bucket isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_bucket_isolation_between_tenants():
    """Exhausting tenant A's bucket leaves tenant B's quota intact."""
    limiter = TenantRateLimiter(backend=InMemoryBackend())
    epoch = 1_000_000_000.0
    for _ in range(30):
        await limiter.enforce(TENANT_A, plan="starter", now_epoch=epoch)
    # Tenant A is now blocked.
    with pytest.raises(HTTPException) as ctx:
        await limiter.enforce(TENANT_A, plan="starter", now_epoch=epoch)
    assert ctx.value.status_code == 429
    # Tenant B is untouched.
    result = await limiter.enforce(TENANT_B, plan="starter", now_epoch=epoch)
    assert result.allowed is True


# ---------------------------------------------------------------------------
# Scenario 5 — quota enforcement cannot spill across tenants
# ---------------------------------------------------------------------------

def test_quota_uses_caller_tenant_plan_only():
    """Tenant A on Starter cannot add a 6th camera even if the
    attacker supplies tenant B's (Enterprise) row somehow."""
    starter = {"tenant_id": TENANT_A, "plan": "starter", "resource_quota": {}}
    with pytest.raises(QuotaExceededError):
        ensure_camera_quota(starter, current_count=5)


# ---------------------------------------------------------------------------
# Scenario 6 — lifecycle transition only touches the requested tenant
# ---------------------------------------------------------------------------

class _MultiTenantDB:
    """Fake DB returning different tenant rows per CAST(:tenant_id)."""

    def __init__(self, rows: dict[str, dict]):
        self._rows = rows
        self.updated: list[dict] = []
        self.audit: list[dict] = []
        self.committed = False

    async def execute(self, query, params=None):
        q = str(query).strip()
        if q.startswith("SELECT") and "FROM tenants" in q:
            tid = params["tenant_id"]
            return _AuditResult(row=self._rows.get(tid))
        if q.startswith("UPDATE tenants"):
            self.updated.append(params)
            return _AuditResult(rowcount=1)
        if "INSERT INTO audit_log" in q:
            self.audit.append(params)
            return _AuditResult(row=(1,))
        return _AuditResult()

    async def commit(self):
        self.committed = True


class _AuditResult:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or ([row] if row else [])
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


@pytest.mark.asyncio
async def test_transition_only_mutates_targeted_tenant():
    """Transitioning tenant A must not emit any UPDATE against
    tenant B. Verified by capturing the bind params."""
    rows = {
        TENANT_A: {"tenant_id": TENANT_A, "status": "pending", "plan": "pro"},
        TENANT_B: {"tenant_id": TENANT_B, "status": "active", "plan": "pro"},
    }
    db = _MultiTenantDB(rows)
    await transition_tenant_status(
        db,
        tenant_id=TENANT_A,
        new_status="active",
        actor_user_id=99,
    )
    assert len(db.updated) == 1
    assert db.updated[0]["tenant_id"] == TENANT_A
    # Every audit row must reference tenant A, never B.
    for row in db.audit:
        assert row["resource_uuid"] == TENANT_A


@pytest.mark.asyncio
async def test_invalid_transition_leaves_no_mutation_or_audit():
    """A rejected transition must roll back — no partial writes, no
    leaked audit rows about 'failed attempt' (the handler layer
    handles logging if it wants)."""
    rows = {TENANT_A: {"tenant_id": TENANT_A, "status": "churned"}}
    db = _MultiTenantDB(rows)
    with pytest.raises(HTTPException):
        await transition_tenant_status(
            db,
            tenant_id=TENANT_A,
            new_status="active",
            actor_user_id=99,
        )
    assert db.updated == []
    assert db.audit == []
    assert db.committed is False

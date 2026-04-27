"""Tests for T1-05 — get_current_tenant FastAPI dependency."""

import hashlib

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from shoplift_detector.app.core.tenant_auth import (
    API_KEY_PREFIX,
    get_current_tenant,
)
from shoplift_detector.app.db.repository.tenants import hash_api_key


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------

def test_hash_api_key_is_sha256_hex():
    raw = "sk_live_deadbeefcafebabe"
    assert hash_api_key(raw) == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # Hex length: SHA-256 → 32 bytes → 64 hex chars.
    assert len(hash_api_key(raw)) == 64


def test_hash_api_key_is_deterministic():
    raw = "sk_live_deadbeefcafebabe"
    assert hash_api_key(raw) == hash_api_key(raw)


def test_hash_api_key_differs_for_different_inputs():
    assert hash_api_key("sk_live_a") != hash_api_key("sk_live_b")


# ---------------------------------------------------------------------------
# Dependency behavior
# ---------------------------------------------------------------------------

class _FakeMappingResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


class _FakeDB:
    """Minimal async DB double that returns a pre-seeded tenant row."""

    def __init__(self, row=None):
        self._row = row
        self.query_text: str | None = None
        self.query_params: dict | None = None

    async def execute(self, query, params=None):
        self.query_text = str(query)
        self.query_params = params
        return _FakeMappingResult(row=self._row)


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _active_tenant_row(api_key_hash: str) -> dict:
    return {
        "tenant_id": "11111111-2222-3333-4444-555555555555",
        "legal_name": "Demo LLC",
        "display_name": "Demo",
        "email": "demo@sentry.mn",
        "phone": None,
        "status": "active",
        "plan": "pro",
        "created_at": None,
        "trial_ends_at": None,
        "current_period_end": None,
        "payment_method_id": None,
        "resource_quota": {"max_cameras": 50},
    }


@pytest.mark.asyncio
async def test_returns_tenant_for_valid_active_key():
    raw = API_KEY_PREFIX + "x" * 32
    db = _FakeDB(row=_active_tenant_row(hash_api_key(raw)))

    tenant = await get_current_tenant(db=db, credentials=_creds(raw))

    assert tenant["status"] == "active"
    assert tenant["email"] == "demo@sentry.mn"
    # The lookup must hash before the query — raw key never travels.
    assert db.query_params["api_key_hash"] == hash_api_key(raw)
    assert raw not in db.query_params["api_key_hash"]


@pytest.mark.asyncio
async def test_missing_credentials_rejected_401():
    db = _FakeDB()
    with pytest.raises(HTTPException) as ctx:
        await get_current_tenant(db=db, credentials=None)
    assert ctx.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert ctx.value.headers.get("WWW-Authenticate", "").startswith("Bearer")


@pytest.mark.asyncio
async def test_empty_token_rejected_401():
    db = _FakeDB()
    with pytest.raises(HTTPException) as ctx:
        await get_current_tenant(db=db, credentials=_creds(""))
    assert ctx.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_prefix_rejected_before_db_lookup():
    db = _FakeDB()
    with pytest.raises(HTTPException) as ctx:
        await get_current_tenant(
            db=db, credentials=_creds("random-opaque-token")
        )
    assert ctx.value.status_code == 401
    # Never queried the DB — short-circuit saves a round-trip.
    assert db.query_text is None


@pytest.mark.asyncio
async def test_unknown_key_rejected_401():
    raw = API_KEY_PREFIX + "unknown"
    db = _FakeDB(row=None)
    with pytest.raises(HTTPException) as ctx:
        await get_current_tenant(db=db, credentials=_creds(raw))
    assert ctx.value.status_code == 401


@pytest.mark.parametrize("status_value", [
    "pending", "suspended", "grace", "churned", "deleted",
])
@pytest.mark.asyncio
async def test_non_active_tenant_rejected_with_generic_401(status_value):
    raw = API_KEY_PREFIX + "y" * 32
    row = _active_tenant_row(hash_api_key(raw))
    row["status"] = status_value
    db = _FakeDB(row=row)

    with pytest.raises(HTTPException) as ctx:
        await get_current_tenant(db=db, credentials=_creds(raw))

    # Same 401 for every non-active status — we don't leak lifecycle
    # state to a caller that may have a stolen key.
    assert ctx.value.status_code == 401
    assert ctx.value.detail == "Invalid API key"


# ---------------------------------------------------------------------------
# T7-01 — org_id → tenant_id resolver
# ---------------------------------------------------------------------------

class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeScalarDB:
    """Async DB double for `scalar_one_or_none()` queries."""

    def __init__(self, value):
        self._value = value
        self.query_text: str | None = None
        self.query_params: dict | None = None

    async def execute(self, query, params=None):
        self.query_text = str(query)
        self.query_params = params
        return _FakeScalarResult(self._value)


@pytest.mark.asyncio
async def test_get_tenant_id_for_organization_returns_str_when_mapped():
    """When the map row exists, we return the UUID as a canonical string
    so JWT encoding (JSON) can accept it without uuid→str conversion
    at every call site."""
    from shoplift_detector.app.db.repository.tenants import TenantRepository

    import uuid
    tenant_uuid = uuid.UUID("11111111-2222-3333-4444-555555555555")
    db = _FakeScalarDB(value=tenant_uuid)

    repo = TenantRepository(db)
    result = await repo.get_tenant_id_for_organization(42)

    assert result == str(tenant_uuid)
    assert db.query_params == {"organization_id": 42}
    assert "organization_tenant_map" in db.query_text


@pytest.mark.asyncio
async def test_get_tenant_id_for_organization_returns_none_when_unmapped():
    """Pre-migration orgs have no map row — resolver returns None so
    login continues to work, just without tenant_id in the JWT."""
    from shoplift_detector.app.db.repository.tenants import TenantRepository

    db = _FakeScalarDB(value=None)
    repo = TenantRepository(db)

    assert await repo.get_tenant_id_for_organization(999) is None


@pytest.mark.asyncio
async def test_get_tenant_id_for_organization_short_circuits_on_none():
    """`None` org_id (unclaimed user) skips the DB round-trip entirely."""
    from shoplift_detector.app.db.repository.tenants import TenantRepository

    db = _FakeScalarDB(value=None)
    repo = TenantRepository(db)

    assert await repo.get_tenant_id_for_organization(None) is None
    assert db.query_text is None, "expected no DB call for null org_id"

"""Regression tests — backend 403 on frontend super-admin routes.

Frontend (`security-web/src/App.jsx:80-87`) gates `/admin/control` behind
a client-side `user.role === 'super_admin'` check. That guard is UX-only —
an attacker can edit `localStorage` and land on the page. The real
boundary is backend `require_super_admin` returning 403.

This file pins that contract: every admin endpoint that the frontend
reaches from `DashboardAdmin.jsx` must refuse a non-super-admin caller.
Uses real JWTs (via the `auth_token` fixture) rather than dependency
overrides so the whole extract→decode→role path is exercised.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.core.security import create_access_token
from app.db.session import get_db
from fastapi import HTTPException

from shoplift_detector.main import app


@pytest.fixture
def admin_role_headers():
    """`admin` role is below super_admin — must still 403 on super-admin routes."""
    token = create_access_token(data={
        "sub": "admin_user",
        "role": "admin",
        "org_id": 1,
        "user_id": 7,
        "tenant_id": "11111111-1111-1111-1111-111111111111",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def _stub_db():
    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Endpoints DashboardAdmin.jsx hits — all must 403 for non-super-admin.
# ---------------------------------------------------------------------------

ADMIN_READ_ENDPOINTS = [
    ("GET", "/api/v1/admin/organizations"),
    ("GET", "/api/v1/admin/users"),
    ("GET", "/api/v1/admin/stats"),
]

ADMIN_WRITE_ENDPOINTS = [
    ("POST", "/api/v1/admin/organizations", {"name": "Acme"}),
    ("DELETE", "/api/v1/admin/organizations/1", None),
    ("PUT", "/api/v1/admin/users/1/role", {"role": "admin"}),
    ("PUT", "/api/v1/admin/users/1/organization", {"organization_id": 1}),
    ("DELETE", "/api/v1/admin/users/1", None),
]


@pytest.mark.parametrize("method,path", ADMIN_READ_ENDPOINTS)
async def test_regular_user_forbidden_on_admin_reads(
    client, auth_headers, _stub_db, method, path
):
    resp = await client.request(method, path, headers=auth_headers)
    assert resp.status_code == 403, (
        f"{method} {path} must refuse role='user' with 403, got {resp.status_code}"
    )


@pytest.mark.parametrize("method,path", ADMIN_READ_ENDPOINTS)
async def test_admin_role_forbidden_on_super_admin_reads(
    client, admin_role_headers, _stub_db, method, path
):
    """`admin` is still below `super_admin` — admin endpoints reject it."""
    resp = await client.request(method, path, headers=admin_role_headers)
    assert resp.status_code == 403


@pytest.mark.parametrize("method,path,body", ADMIN_WRITE_ENDPOINTS)
async def test_regular_user_forbidden_on_admin_writes(
    client, auth_headers, _stub_db, method, path, body
):
    resp = await client.request(method, path, headers=auth_headers, json=body)
    assert resp.status_code == 403


async def test_unauthenticated_admin_call_returns_401(client, _stub_db):
    """No bearer → 401, never 200, never silent pass."""
    resp = await client.get("/api/v1/admin/organizations")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unit — the dependency itself. Belt-and-braces for the HTTP tests above.
# ---------------------------------------------------------------------------

async def test_require_super_admin_unit_raises_403_for_admin_role():
    from app.core.security import require_super_admin

    admin_user = {"username": "bob", "role": "admin", "user_id": 7}
    with pytest.raises(HTTPException) as ctx:
        await require_super_admin(admin_user)
    assert ctx.value.status_code == 403


async def test_require_super_admin_unit_raises_403_for_user_role():
    from app.core.security import require_super_admin

    regular_user = {"username": "alice", "role": "user", "user_id": 42}
    with pytest.raises(HTTPException) as ctx:
        await require_super_admin(regular_user)
    assert ctx.value.status_code == 403


async def test_require_super_admin_unit_accepts_super_admin_role():
    """Positive control — the dependency must let super_admin through
    unchanged so we know the 403 above isn't a blanket rejection."""
    from app.core.security import require_super_admin

    sa = {"username": "root", "role": "super_admin", "user_id": 1}
    result = await require_super_admin(sa)
    assert result["role"] == "super_admin"

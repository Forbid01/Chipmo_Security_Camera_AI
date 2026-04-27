"""T5-09 — customer-portal viewer endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.db.session import get_db


@pytest.fixture
def _stub_db():
    from shoplift_detector.main import app

    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield
    app.dependency_overrides.pop(get_db, None)


async def test_escalations_require_auth(client, _stub_db):
    resp = await client.get("/api/v1/alerts/42/escalations")
    assert resp.status_code == 401


async def test_escalations_404_when_alert_missing(client, auth_headers, _stub_db):
    from app.api.v1 import escalations as esc_mod

    class _NoAlertRepo:
        def __init__(self, _db): pass

        async def get_by_id(self, _id):
            return None

    with patch.object(esc_mod, "AlertRepository", _NoAlertRepo):
        resp = await client.get(
            "/api/v1/alerts/999/escalations", headers=auth_headers
        )
    assert resp.status_code == 404


async def test_escalations_404_on_cross_tenant_alert(
    client, auth_headers, _stub_db
):
    """Same-tenant 403 would let attackers enumerate alert_ids; we
    return 404 so they can't distinguish 'exists, no access' from
    'does not exist'."""
    from app.api.v1 import escalations as esc_mod

    class _OtherTenantAlertRepo:
        def __init__(self, _db): pass

        async def get_by_id(self, _id):
            # auth_headers fixture uses org_id=None; this alert claims a
            # different org → the handler's 404 path triggers.
            return {"id": 1, "organization_id": 9999}

    class _UnusedEscRepo:
        def __init__(self, _db): pass

        async def list_for_alert(self, _id):
            return []

    with patch.object(esc_mod, "AlertRepository", _OtherTenantAlertRepo), \
         patch.object(esc_mod, "AlertEscalationRepository", _UnusedEscRepo):
        resp = await client.get(
            "/api/v1/alerts/1/escalations", headers=auth_headers
        )
    assert resp.status_code == 404


async def test_escalations_happy_path_returns_rows(
    client, auth_headers, _stub_db
):
    from app.api.v1 import escalations as esc_mod

    class _OwnedAlertRepo:
        def __init__(self, _db): pass

        async def get_by_id(self, _id):
            # org_id=None matches auth_headers' None so the handler
            # treats this as "same tenant, allow".
            return {"id": 1, "organization_id": None}

    sample_rows = [
        {"id": 10, "channel": "telegram", "recipient": "chat-1"},
        {"id": 11, "channel": "email", "recipient": "owner@test.mn"},
    ]

    class _SpyEscRepo:
        def __init__(self, _db): pass

        async def list_for_alert(self, _id):
            return sample_rows

    with patch.object(esc_mod, "AlertRepository", _OwnedAlertRepo), \
         patch.object(esc_mod, "AlertEscalationRepository", _SpyEscRepo):
        resp = await client.get(
            "/api/v1/alerts/1/escalations", headers=auth_headers
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert_id"] == 1
    assert [r["channel"] for r in body["escalations"]] == ["telegram", "email"]


async def test_super_admin_sees_any_tenants_escalations(
    client, admin_headers, _stub_db
):
    """super_admin bypasses the cross-tenant 404 path so support can
    diagnose issues across orgs."""
    from app.api.v1 import escalations as esc_mod

    class _AnyTenantAlertRepo:
        def __init__(self, _db): pass

        async def get_by_id(self, _id):
            return {"id": 1, "organization_id": 777}

    class _EmptyEscRepo:
        def __init__(self, _db): pass

        async def list_for_alert(self, _id):
            return []

    with patch.object(esc_mod, "AlertRepository", _AnyTenantAlertRepo), \
         patch.object(esc_mod, "AlertEscalationRepository", _EmptyEscRepo):
        resp = await client.get(
            "/api/v1/alerts/1/escalations", headers=admin_headers
        )
    assert resp.status_code == 200

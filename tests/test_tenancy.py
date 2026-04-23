"""Tests for T02-21 — tenant access dependencies.

Covers the `app.core.tenancy` dependency module directly. End-to-end
cross-tenant regression suite (the "orgA cannot reach orgB" matrix)
is its own task (T02-23) and lives in a separate file.

Core invariants locked here:
- super_admin short-circuits every check
- missing resource → 404
- cross-tenant access → 404 (not 403) to prevent enumeration
- user without org_id → 404 on any protected resource
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.tenancy import (
    require_alert_access,
    require_camera_access,
    require_case_access,
    require_store_access,
)
from fastapi import HTTPException

SUPER_ADMIN = {"role": "super_admin", "user_id": 1, "org_id": None}
ORG_A_ADMIN = {"role": "admin", "user_id": 10, "org_id": 100}
ORG_B_ADMIN = {"role": "admin", "user_id": 20, "org_id": 200}
ORPHAN_USER = {"role": "user", "user_id": 30, "org_id": None}


def _mapping_result(row):
    """Shape compatible with .mappings().fetchone() + .fetchone()."""
    class R:
        def mappings(self_inner):
            return self_inner

        def fetchone(self_inner):
            return row

    return R()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_store_access_returns_store_for_owner_org():
    from app.db.repository import stores as stores_repo

    async def fake_get_by_id(self, store_id):
        return {"id": store_id, "name": "A", "organization_id": 100}

    original = stores_repo.StoreRepository.get_by_id
    stores_repo.StoreRepository.get_by_id = fake_get_by_id
    try:
        db = AsyncMock()
        result = await require_store_access(1, ORG_A_ADMIN, db)
        assert result["organization_id"] == 100
    finally:
        stores_repo.StoreRepository.get_by_id = original


@pytest.mark.asyncio
async def test_require_store_access_super_admin_shortcircuits():
    from app.db.repository import stores as stores_repo

    async def fake_get_by_id(self, store_id):
        return {"id": store_id, "organization_id": 999}

    original = stores_repo.StoreRepository.get_by_id
    stores_repo.StoreRepository.get_by_id = fake_get_by_id
    try:
        result = await require_store_access(1, SUPER_ADMIN, AsyncMock())
        assert result["organization_id"] == 999
    finally:
        stores_repo.StoreRepository.get_by_id = original


@pytest.mark.asyncio
async def test_require_store_access_cross_tenant_returns_404_not_403():
    from app.db.repository import stores as stores_repo

    async def fake_get_by_id(self, store_id):
        return {"id": store_id, "organization_id": 200}

    original = stores_repo.StoreRepository.get_by_id
    stores_repo.StoreRepository.get_by_id = fake_get_by_id
    try:
        with pytest.raises(HTTPException) as exc:
            await require_store_access(1, ORG_A_ADMIN, AsyncMock())
        # 404 specifically — 403 would leak that the store exists.
        assert exc.value.status_code == 404
    finally:
        stores_repo.StoreRepository.get_by_id = original


@pytest.mark.asyncio
async def test_require_store_access_missing_store_404():
    from app.db.repository import stores as stores_repo

    async def fake_get_by_id(self, store_id):
        return None

    original = stores_repo.StoreRepository.get_by_id
    stores_repo.StoreRepository.get_by_id = fake_get_by_id
    try:
        with pytest.raises(HTTPException) as exc:
            await require_store_access(1, ORG_A_ADMIN, AsyncMock())
        assert exc.value.status_code == 404
    finally:
        stores_repo.StoreRepository.get_by_id = original


@pytest.mark.asyncio
async def test_require_store_access_orphan_user_cannot_reach_any_store():
    from app.db.repository import stores as stores_repo

    async def fake_get_by_id(self, store_id):
        return {"id": store_id, "organization_id": 100}

    original = stores_repo.StoreRepository.get_by_id
    stores_repo.StoreRepository.get_by_id = fake_get_by_id
    try:
        with pytest.raises(HTTPException) as exc:
            await require_store_access(1, ORPHAN_USER, AsyncMock())
        assert exc.value.status_code == 404
    finally:
        stores_repo.StoreRepository.get_by_id = original


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def _camera_row(camera_id=1, organization_id=100):
    return {
        "id": camera_id,
        "name": "cam",
        "url": "rtsp://x",
        "camera_type": "rtsp",
        "store_id": 1,
        "organization_id": organization_id,
        "is_active": True,
        "is_ai_enabled": True,
    }


@pytest.mark.asyncio
async def test_require_camera_access_same_org_ok():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_mapping_result(_camera_row()))
    cam = await require_camera_access(1, ORG_A_ADMIN, db)
    assert cam["id"] == 1


@pytest.mark.asyncio
async def test_require_camera_access_cross_tenant_404():
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_mapping_result(_camera_row(organization_id=200))
    )
    with pytest.raises(HTTPException) as exc:
        await require_camera_access(1, ORG_A_ADMIN, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_camera_access_missing_404():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_mapping_result(None))
    with pytest.raises(HTTPException) as exc:
        await require_camera_access(42, ORG_A_ADMIN, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_camera_access_super_admin_shortcircuits():
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_mapping_result(_camera_row(organization_id=999))
    )
    cam = await require_camera_access(1, SUPER_ADMIN, db)
    assert cam["organization_id"] == 999


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_alert_access_uses_effective_org_id():
    db = AsyncMock()
    # Alert without its own organization_id — derived from the camera.
    row = {
        "id": 1,
        "person_id": 42,
        "organization_id": None,
        "store_id": 1,
        "camera_id": 7,
        "event_time": None,
        "image_path": None,
        "description": None,
        "effective_org_id": 100,
    }
    db.execute = AsyncMock(return_value=_mapping_result(row))

    alert = await require_alert_access(1, ORG_A_ADMIN, db)
    assert alert["id"] == 1


@pytest.mark.asyncio
async def test_require_alert_access_cross_tenant_404():
    db = AsyncMock()
    row = {
        "id": 1,
        "person_id": 42,
        "organization_id": None,
        "store_id": 1,
        "camera_id": 7,
        "event_time": None,
        "image_path": None,
        "description": None,
        "effective_org_id": 200,
    }
    db.execute = AsyncMock(return_value=_mapping_result(row))

    with pytest.raises(HTTPException) as exc:
        await require_alert_access(1, ORG_A_ADMIN, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_alert_access_missing_404():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_mapping_result(None))
    with pytest.raises(HTTPException) as exc:
        await require_alert_access(99, ORG_A_ADMIN, db)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Case (UUID PK)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_case_access_resolves_effective_org_from_store():
    db = AsyncMock()
    case_id = uuid4()
    row = {
        "id": case_id,
        "store_id": 1,
        "effective_org_id": 100,
    }
    db.execute = AsyncMock(return_value=_mapping_result(row))

    case = await require_case_access(str(case_id), ORG_A_ADMIN, db)
    assert case["id"] == case_id


@pytest.mark.asyncio
async def test_require_case_access_cross_tenant_404():
    db = AsyncMock()
    case_id = uuid4()
    row = {
        "id": case_id,
        "store_id": 1,
        "effective_org_id": 200,
    }
    db.execute = AsyncMock(return_value=_mapping_result(row))

    with pytest.raises(HTTPException) as exc:
        await require_case_access(str(case_id), ORG_A_ADMIN, db)
    assert exc.value.status_code == 404

"""Cross-tenant regression matrix (T02-23).

One fixture builds two organizations (A and B), each with one store,
one camera, and one alert. Every guarded route from T02-12 §4 is hit
with an org-A user's JWT using an org-B resource id. Every such call
must fail with 404 (T02-13 §3.3 enumeration-block principle).

No live Postgres is required — we stub the repositories directly so
the test only exercises the handler-layer guards that T02-21 landed.
This keeps the suite fast and hermetic while still catching any
future regression where a handler drops its `require_*_access`
dependency.
"""

from unittest.mock import AsyncMock, patch

import pytest
from app.core.security import create_access_token
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Two-tenant fixture world
# ---------------------------------------------------------------------------

ORG_A_ID = 100
ORG_B_ID = 200

STORE_A_ID = 11
STORE_B_ID = 22
CAMERA_A_ID = 111
CAMERA_B_ID = 222
ALERT_A_ID = 1111
ALERT_B_ID = 2222


def _user_token(user_id: int, org_id: int, role: str = "admin") -> str:
    return create_access_token({
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "role": role,
        "org_id": org_id,
    })


USER_A_TOKEN = _user_token(user_id=10, org_id=ORG_A_ID)
USER_B_TOKEN = _user_token(user_id=20, org_id=ORG_B_ID)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_store(store_id: int, org_id: int) -> dict:
    return {
        "id": store_id,
        "name": f"store_{store_id}",
        "organization_id": org_id,
        "alert_threshold": 80.0,
        "alert_cooldown": 60,
        "telegram_chat_id": None,
        "address": None,
        "organization_name": f"org_{org_id}",
        "camera_count": 1,
        "created_at": "2026-04-21T00:00:00+00:00",
    }


def _make_camera_row(camera_id: int, store_id: int, org_id: int) -> dict:
    return {
        "id": camera_id,
        "name": f"cam_{camera_id}",
        "url": "rtsp://x",
        "camera_type": "rtsp",
        "store_id": store_id,
        "organization_id": org_id,
        "is_active": True,
        "is_ai_enabled": True,
    }


def _make_alert_row(alert_id: int, store_id: int, camera_id: int, org_id: int) -> dict:
    return {
        "id": alert_id,
        "person_id": 1,
        "organization_id": org_id,
        "store_id": store_id,
        "camera_id": camera_id,
        "event_time": None,
        "image_path": None,
        "description": None,
        "effective_org_id": org_id,
    }


STORE_INDEX = {
    STORE_A_ID: _make_store(STORE_A_ID, ORG_A_ID),
    STORE_B_ID: _make_store(STORE_B_ID, ORG_B_ID),
}
CAMERA_INDEX = {
    CAMERA_A_ID: _make_camera_row(CAMERA_A_ID, STORE_A_ID, ORG_A_ID),
    CAMERA_B_ID: _make_camera_row(CAMERA_B_ID, STORE_B_ID, ORG_B_ID),
}
ALERT_INDEX = {
    ALERT_A_ID: _make_alert_row(ALERT_A_ID, STORE_A_ID, CAMERA_A_ID, ORG_A_ID),
    ALERT_B_ID: _make_alert_row(ALERT_B_ID, STORE_B_ID, CAMERA_B_ID, ORG_B_ID),
}


# ---------------------------------------------------------------------------
# Repository stubs — mounted via autouse fixture
# ---------------------------------------------------------------------------

class _MappingResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


async def _fake_store_get_by_id(self, store_id):
    return STORE_INDEX.get(store_id)


async def _fake_db_execute(self_db, query, params=None):
    """Intercept SELECTs used by require_camera_access /
    require_alert_access. Returns the seeded fixture row keyed off
    the query text.
    """
    q = str(query)
    if "FROM cameras" in q and "WHERE id = :id" in q:
        row = CAMERA_INDEX.get(params.get("id") if params else None)
        return _MappingResult(row)
    if "FROM alerts a" in q and "LEFT JOIN cameras c" in q:
        row = ALERT_INDEX.get(params.get("id") if params else None)
        return _MappingResult(row)
    return _MappingResult(None)


@pytest.fixture(autouse=True)
def _stub_repository_reads(monkeypatch):
    from app.db.repository import stores as stores_repo
    from sqlalchemy.ext.asyncio import AsyncSession

    monkeypatch.setattr(
        stores_repo.StoreRepository, "get_by_id", _fake_store_get_by_id
    )
    monkeypatch.setattr(
        AsyncSession, "execute", _fake_db_execute, raising=False
    )
    yield


@pytest.fixture
async def authed_client():
    """Separate async client fixture so we can drive the full app."""
    from shoplift_detector.main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_a_can_read_own_store(authed_client):
    r = await authed_client.get(
        f"/api/v1/stores/{STORE_A_ID}", headers=_auth_headers(USER_A_TOKEN)
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_org_a_cannot_read_org_b_store_returns_404(authed_client):
    r = await authed_client.get(
        f"/api/v1/stores/{STORE_B_ID}", headers=_auth_headers(USER_A_TOKEN)
    )
    # 404, not 403 — don't leak existence (T02-13 §3.3).
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_read_org_b_store_settings_returns_404(authed_client):
    r = await authed_client.get(
        f"/api/v1/stores/{STORE_B_ID}/settings",
        headers=_auth_headers(USER_A_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_patch_org_b_store_settings_returns_404(authed_client):
    r = await authed_client.patch(
        f"/api/v1/stores/{STORE_B_ID}/settings",
        headers=_auth_headers(USER_A_TOKEN),
        json={"alert_threshold": 42.0},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Video feeds (Critical hazards)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_a_cannot_open_org_b_camera_feed_returns_404(authed_client):
    r = await authed_client.get(
        f"/api/v1/video/feed/{CAMERA_B_ID}",
        headers=_auth_headers(USER_A_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_open_org_b_store_grid_returns_404(authed_client):
    r = await authed_client.get(
        f"/api/v1/video/store/{STORE_B_ID}",
        headers=_auth_headers(USER_A_TOKEN),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Telegram endpoints (High)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_a_cannot_configure_org_b_telegram_returns_404(authed_client):
    r = await authed_client.post(
        "/api/v1/telegram/setup",
        headers=_auth_headers(USER_A_TOKEN),
        json={"store_id": STORE_B_ID, "chat_id": "@attacker"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_test_org_b_telegram_returns_404(authed_client):
    r = await authed_client.post(
        "/api/v1/telegram/test",
        headers=_auth_headers(USER_A_TOKEN),
        json={"store_id": STORE_B_ID, "chat_id": "@attacker"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_delete_org_b_telegram_returns_404(authed_client):
    r = await authed_client.delete(
        f"/api/v1/telegram/{STORE_B_ID}",
        headers=_auth_headers(USER_A_TOKEN),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Feedback endpoints (High)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_a_cannot_feedback_on_org_b_alert_returns_404(authed_client):
    r = await authed_client.post(
        "/api/v1/feedback",
        headers=_auth_headers(USER_A_TOKEN),
        json={
            "alert_id": ALERT_B_ID,
            "feedback_type": "true_positive",
            "notes": "not yours",
        },
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_org_a_feedback_stats_requires_store_id_for_non_super(authed_client):
    # Non-super admin must supply store_id (H-H10 remediation).
    r = await authed_client.get(
        "/api/v1/feedback/stats",
        headers=_auth_headers(USER_A_TOKEN),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_org_a_cannot_query_org_b_feedback_stats_returns_404(authed_client):
    with patch(
        "app.db.repository.feedback_repo.FeedbackRepository.get_stats",
        new=AsyncMock(return_value={"total_feedback": 0}),
    ):
        r = await authed_client.get(
            "/api/v1/feedback/stats",
            headers=_auth_headers(USER_A_TOKEN),
            params={"store_id": STORE_B_ID},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_query_org_b_feedback_learning_status_returns_404(authed_client):
    with patch(
        "app.db.repository.feedback_repo.FeedbackRepository.get_learning_status",
        new=AsyncMock(return_value={}),
    ):
        r = await authed_client.get(
            "/api/v1/feedback/learning-status",
            headers=_auth_headers(USER_A_TOKEN),
            params={"store_id": STORE_B_ID},
        )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Legacy /video_feed routes (Critical)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_super_admin_cannot_hit_legacy_video_feed_returns_403(authed_client):
    # T02-21 gated these behind SuperAdmin; a regular admin must be
    # rejected outright. 403 is fine here because these routes are
    # role-guarded, not tenant-guarded — the caller's org is irrelevant.
    r = await authed_client.get(
        "/video_feed", headers=_auth_headers(USER_A_TOKEN)
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_non_super_admin_cannot_hit_legacy_video_feed_by_id_returns_403(authed_client):
    r = await authed_client.get(
        "/video_feed/mac", headers=_auth_headers(USER_A_TOKEN)
    )
    assert r.status_code == 403

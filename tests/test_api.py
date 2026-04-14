"""Tests for general API endpoints: health, alerts, admin routes."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    """GET /health"""

    @pytest.mark.api
    async def test_health_returns_200(self, client):
        """The health endpoint should always return 200 with status ok."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "cameras" in body
        assert "database" in body

    @pytest.mark.api
    async def test_health_contains_camera_counts(self, client):
        """Health response includes total and connected camera counts."""
        resp = await client.get("/health")
        cameras = resp.json()["cameras"]
        assert "total" in cameras
        assert "connected" in cameras


# ---------------------------------------------------------------------------
# Alerts endpoint (requires auth)
# ---------------------------------------------------------------------------

class TestAlerts:
    """GET /alerts"""

    @pytest.mark.api
    async def test_alerts_requires_auth(self, client):
        """Accessing /alerts without a token returns 401."""
        resp = await client.get("/alerts")
        assert resp.status_code == 401

    @pytest.mark.api
    async def test_alerts_with_valid_token(self, client, auth_headers):
        """Authenticated user can fetch alerts."""
        mock_repo = AsyncMock()
        mock_repo.get_latest_alerts = AsyncMock(return_value=[])

        with patch(
            "shoplift_detector.main.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "shoplift_detector.main.AlertRepository",
            return_value=mock_repo,
        ):
            resp = await client.get("/alerts", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert isinstance(body["data"], list)

    @pytest.mark.api
    async def test_alerts_with_invalid_token(self, client):
        """An invalid token returns 401."""
        resp = await client.get(
            "/alerts",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin endpoints (require super_admin role)
# ---------------------------------------------------------------------------

class TestAdminEndpoints:
    """Admin routes under /admin/* require super_admin role."""

    @pytest.mark.api
    async def test_admin_users_requires_auth(self, client):
        """GET /admin/users without auth returns 401."""
        resp = await client.get("/admin/users")
        assert resp.status_code == 401

    @pytest.mark.api
    async def test_admin_users_regular_user_forbidden(self, client, auth_headers):
        """A regular user (role=user) is forbidden from admin endpoints."""
        resp = await client.get("/admin/users", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.api
    async def test_admin_stats_requires_super_admin(self, client, auth_headers):
        """GET /admin/stats with a regular user token returns 403."""
        resp = await client.get("/admin/stats", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.api
    async def test_admin_organizations_requires_super_admin(self, client, auth_headers):
        """GET /admin/organizations with a regular user returns 403."""
        resp = await client.get("/admin/organizations", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.api
    async def test_admin_stats_allowed_for_super_admin(self, client, admin_headers):
        """A super_admin can access /admin/stats."""
        mock_user_repo = AsyncMock()
        mock_user_repo.get_stats = AsyncMock(return_value={
            "users": 10,
            "organizations": 2,
            "cameras": 5,
            "alerts": 100,
        })

        mock_store_repo = AsyncMock()
        mock_store_repo.count = AsyncMock(return_value=3)

        with patch(
            "shoplift_detector.app.api.v1.admin.get_db",
            return_value=AsyncMock(
                __anext__=AsyncMock(return_value=MagicMock()),
            ),
        ), patch(
            "shoplift_detector.app.api.v1.admin.UserRepository",
            return_value=mock_user_repo,
        ), patch(
            "shoplift_detector.app.api.v1.admin.StoreRepository",
            return_value=mock_store_repo,
        ):
            resp = await client.get("/admin/stats", headers=admin_headers)

        assert resp.status_code == 200

    @pytest.mark.api
    async def test_admin_users_allowed_for_super_admin(self, client, admin_headers):
        """A super_admin can access /admin/users."""
        mock_repo = AsyncMock()
        mock_repo.get_all_users = AsyncMock(return_value=[])

        with patch(
            "shoplift_detector.app.api.v1.admin.get_db",
            return_value=AsyncMock(
                __anext__=AsyncMock(return_value=MagicMock()),
            ),
        ), patch(
            "shoplift_detector.app.api.v1.admin.UserRepository",
            return_value=mock_repo,
        ):
            resp = await client.get("/admin/users", headers=admin_headers)

        assert resp.status_code == 200

    @pytest.mark.api
    async def test_admin_delete_user_requires_super_admin(self, client, auth_headers):
        """DELETE /admin/users/{id} with a regular user returns 403."""
        resp = await client.delete("/admin/users/1", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.api
    async def test_admin_alerts_requires_super_admin(self, client, auth_headers):
        """GET /admin/alerts with a regular user returns 403."""
        resp = await client.get("/admin/alerts", headers=auth_headers)
        assert resp.status_code == 403

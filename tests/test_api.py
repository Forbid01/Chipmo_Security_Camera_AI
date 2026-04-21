from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.security import get_current_user
from app.db.session import get_db

from shoplift_detector.main import app

# ---------------------------------------------------------------------------
# Alerts endpoint
# ---------------------------------------------------------------------------

class TestAlerts:
    @pytest.mark.api
    async def test_alerts_with_valid_token(self, client, auth_headers):
        """Authenticated user can fetch alerts."""

    # 1. Mock хийх өгөгдөл
        mock_user = {"username": "testuser", "role": "user", "org_id": 1}
        mock_alerts = [{"id": 1, "image_path": "test.jpg"}]

        mock_repo = AsyncMock()
        mock_repo.get_latest_alerts = AsyncMock(return_value=mock_alerts)

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: MagicMock()
        with patch("app.api.v1.alerts.AlertRepository", return_value=mock_repo):
            resp = await client.get("/api/v1/alerts", headers=auth_headers)

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

class TestAdminEndpoints:
    @pytest.mark.api
    async def test_admin_stats_allowed_for_super_admin(self, client, admin_headers):
        """A super_admin can access /admin/stats."""
        # Super admin эрхээр override хийх
        app.dependency_overrides[get_current_user] = lambda: {
            "role": "super_admin", "username": "admin"
        }

        mock_user_repo = AsyncMock()
        mock_user_repo.get_stats = AsyncMock(return_value={
            "users": 10, "organizations": 2, "cameras": 5, "alerts": 100
        })

        mock_store_repo = AsyncMock()
        mock_store_repo.count = AsyncMock(return_value=3)

        # Admin route-үүд нь app/api/v1/admin.py дотор байгаа тул тэнд нь патч хийнэ
        app.dependency_overrides[get_db] = lambda: MagicMock()
        with patch("app.api.v1.admin.UserRepository", return_value=mock_user_repo), \
             patch("app.api.v1.admin.StoreRepository", return_value=mock_store_repo):
            resp = await client.get("/api/v1/admin/stats", headers=admin_headers)

        app.dependency_overrides.clear()
        assert resp.status_code == 200

    @pytest.mark.api
    async def test_admin_users_allowed_for_super_admin(self, client, admin_headers):
        """A super_admin can access /admin/users."""
        app.dependency_overrides[get_current_user] = lambda: {"role": "super_admin"}

        mock_repo = AsyncMock()
        mock_repo.get_all_users = AsyncMock(return_value=[])

        app.dependency_overrides[get_db] = lambda: MagicMock()
        with patch("app.api.v1.admin.UserRepository", return_value=mock_repo):
            resp = await client.get("/api/v1/admin/users", headers=admin_headers)

        app.dependency_overrides.clear()
        assert resp.status_code == 200

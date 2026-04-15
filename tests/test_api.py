from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.security import get_current_user

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

        # 2. get_current_user-ыг шууд патчлах (Учир нь Depends биш шууд дуудагдсан)
        with patch("app.core.security.get_current_user", new_callable=AsyncMock) as mock_auth, \
            patch("app.db.session.AsyncSessionLocal") as mock_session_local, \
            patch("app.db.repository.alerts.AlertRepository", return_value=mock_repo):

            # get_current_user дуудагдахад mock_user-ыг буцаана
            mock_auth.return_value = mock_user

            # Session setup
            mock_session = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_session

            resp = await client.get("/alerts", headers=auth_headers)

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
        with patch("app.api.v1.admin.get_db") as mock_get_db, \
             patch("app.api.v1.admin.UserRepository", return_value=mock_user_repo), \
             patch("app.api.v1.admin.StoreRepository", return_value=mock_store_repo):

            # get_db() generator-ыг mock хийх
            mock_db = MagicMock()
            mock_get_db.return_value.__anext__.return_value = mock_db

            resp = await client.get("/admin/stats", headers=admin_headers)

        app.dependency_overrides.clear()
        assert resp.status_code == 200

    @pytest.mark.api
    async def test_admin_users_allowed_for_super_admin(self, client, admin_headers):
        """A super_admin can access /admin/users."""
        app.dependency_overrides[get_current_user] = lambda: {"role": "super_admin"}

        mock_repo = AsyncMock()
        mock_repo.get_all_users = AsyncMock(return_value=[])

        with patch("app.api.v1.admin.get_db") as mock_get_db, \
             patch("app.api.v1.admin.UserRepository", return_value=mock_repo):

            mock_get_db.return_value.__anext__.return_value = MagicMock()
            resp = await client.get("/admin/users", headers=admin_headers)

        app.dependency_overrides.clear()
        assert resp.status_code == 200

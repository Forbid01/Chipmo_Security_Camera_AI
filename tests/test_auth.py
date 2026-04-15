"""Tests for authentication endpoints: /register, /token, /users/me."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:
    """POST /register"""

    @pytest.mark.auth
    async def test_register_valid_user(self, client, test_user_data):
        mock_repo = AsyncMock()
        mock_repo.get_by_identifier = AsyncMock(return_value=None)
        mock_repo.get_by_email = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=42)

        # FastAPI-ийн dependency injection-ийг патчлах нь хамгийн найдвартай арга
        with patch("shoplift_detector.main.get_db") as mock_get_db:
            mock_get_db.return_value.__anext__.return_value = AsyncMock()
            
            # UserRepository патчлахдаа main.py эсвэл routers/auth.py-г ашигла
            with patch("shoplift_detector.main.UserRepository", return_value=mock_repo):
                resp = await client.post("/register", json=test_user_data)

        assert resp.status_code == 200
        body = resp.json()
        assert "user_id" in body or "message" in body

    @pytest.mark.auth
    async def test_register_duplicate_username(self, client, test_user_data, test_user_db_row):
        """Registering with an existing username returns 400."""
        mock_repo = AsyncMock()
        mock_repo.get_by_identifier = AsyncMock(return_value=test_user_db_row)

        with patch(
            "shoplift_detector.app.db.session.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "shoplift_detector.app.repositories.user.UserRepository",
            return_value=mock_repo,
        ):
            resp = await client.post("/register", json=test_user_data)

        assert resp.status_code == 400
        assert "бүртгэлтэй" in resp.json()["detail"]

    @pytest.mark.auth
    async def test_register_weak_password(self, client):
        """A password that fails the schema validator returns 422."""
        payload = {
            "username": "weakuser",
            "email": "weak@example.com",
            "password": "short",
            "full_name": "Weak User",
        }
        resp = await client.post("/register", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------

class TestLogin:
    """POST /token (OAuth2 form-data login)"""

    @pytest.mark.auth
    async def test_login_valid_credentials(self, client, test_user_db_row):
        """Valid username + password returns an access_token."""
        mock_repo = AsyncMock()
        mock_repo.get_by_identifier = AsyncMock(return_value=test_user_db_row)

        with patch(
            "shoplift_detector.app.db.session.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "shoplift_detector.main.UserRepository",
            return_value=mock_repo,
        ):
            resp = await client.post(
                "/token",
                data={"username": "testuser", "password": "StrongP@ss1!"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    @pytest.mark.auth
    async def test_login_wrong_password(self, client, test_user_db_row):
        """Wrong password returns 401."""
        mock_repo = AsyncMock()
        mock_repo.get_by_identifier = AsyncMock(return_value=test_user_db_row)

        with patch(
            "shoplift_detector.app.db.session.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "shoplift_detector.app.repositories.user.UserRepository",
            return_value=mock_repo,
        ):
            resp = await client.post(
                "/token",
                data={"username": "testuser", "password": "WrongPass1!"},
            )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /users/me tests
# ---------------------------------------------------------------------------

class TestUsersMe:
    """GET /users/me"""

    @pytest.mark.auth
    async def test_users_me_authenticated(self, client, auth_headers, test_user_db_row):
        """Authenticated request returns user profile."""
        mock_repo = AsyncMock()
        mock_repo.get_by_identifier = AsyncMock(return_value=test_user_db_row)

        with patch(
            "shoplift_detector.app.db.session.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "shoplift_detector.app.repositories.user.UserRepository",
            return_value=mock_repo,
        ):
            resp = await client.get("/users/me", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "testuser"
        assert body["email"] == "testuser@example.com"
        assert body["role"] == "user"

    @pytest.mark.auth
    async def test_users_me_no_token(self, client):
        """Request without auth token returns 401."""
        resp = await client.get("/users/me")
        assert resp.status_code == 401
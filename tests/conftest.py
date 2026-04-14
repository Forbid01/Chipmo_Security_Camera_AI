"""Shared pytest fixtures for the Chipmo Security Camera AI test suite."""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# Ensure the shoplift_detector package is importable
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOPLIFT_DIR = os.path.join(BASE_DIR, "shoplift_detector")
if SHOPLIFT_DIR not in sys.path:
    sys.path.insert(0, SHOPLIFT_DIR)

# Set required env vars before importing the app so Settings() doesn't fail
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("DEBUG", "true")


# ---------------------------------------------------------------------------
# Patch heavy services BEFORE the app module is imported so that the lifespan
# startup code does not attempt to connect to a real database or start camera
# threads.
# ---------------------------------------------------------------------------

_mock_engine = MagicMock()
_mock_engine.begin = MagicMock(return_value=AsyncMock())

with patch("shoplift_detector.app.db.session.engine", _mock_engine):
    from shoplift_detector.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async HTTP test client backed by the FastAPI app.

    Uses httpx.AsyncClient with ASGITransport so that no real server is
    started and no lifespan events fire (avoids DB/camera side-effects).
    """
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def mock_db_session():
    """A fully mocked async database session."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def test_user_data():
    """Sample user registration payload that satisfies all validators."""
    return {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "StrongP@ss1!",
        "full_name": "Test User",
        "phone_number": "+97699001122",
    }


@pytest.fixture
def test_user_db_row():
    """A dict that mimics what UserRepository.get_by_identifier returns."""
    from shoplift_detector.app.core.security import get_password_hash

    return {
        "id": 1,
        "username": "testuser",
        "email": "testuser@example.com",
        "hashed_password": get_password_hash("StrongP@ss1!"),
        "full_name": "Test User",
        "role": "user",
        "organization_id": None,
        "organization_name": None,
        "phone_number": "+97699001122",
    }


@pytest.fixture
def auth_token(test_user_db_row):
    """A valid JWT access token for the test user."""
    from shoplift_detector.app.core.security import create_access_token

    return create_access_token(data={
        "sub": test_user_db_row["username"],
        "role": test_user_db_row["role"],
        "org_id": test_user_db_row["organization_id"],
        "user_id": test_user_db_row["id"],
    })


@pytest.fixture
def admin_token():
    """A valid JWT access token for a super_admin user."""
    from shoplift_detector.app.core.security import create_access_token

    return create_access_token(data={
        "sub": "superadmin",
        "role": "super_admin",
        "org_id": None,
        "user_id": 999,
    })


@pytest.fixture
def auth_headers(auth_token):
    """Authorization headers for a regular user."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def admin_headers(admin_token):
    """Authorization headers for a super_admin."""
    return {"Authorization": f"Bearer {admin_token}"}

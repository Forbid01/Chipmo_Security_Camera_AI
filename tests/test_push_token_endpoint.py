"""T5-07 — POST/DELETE /api/v1/push/tokens."""

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


async def test_register_requires_auth(client, _stub_db):
    resp = await client.post("/api/v1/push/tokens", json={
        "token": "device-token-abc", "platform": "ios"
    })
    # No bearer / cookie → 401 from get_current_user.
    assert resp.status_code == 401


async def test_register_rejects_unknown_platform(client, auth_headers, _stub_db):
    resp = await client.post(
        "/api/v1/push/tokens",
        json={"token": "device-token-abc", "platform": "windows-phone"},
        headers=auth_headers,
    )
    # Literal["ios","android","web"] rejects unknown → 422.
    assert resp.status_code == 422


async def test_register_503_on_pre_migration_schema(client, auth_headers, _stub_db):
    """When the table hasn't been created yet the repo returns None —
    the endpoint must translate that to 503 so the client knows the
    server isn't ready rather than pretending success."""
    from app.api.v1 import push as push_mod

    class _NoTableRepo:
        def __init__(self, _db): pass

        async def register(self, **_kwargs):
            return None

    with patch.object(push_mod, "PushTokenRepository", _NoTableRepo):
        resp = await client.post(
            "/api/v1/push/tokens",
            json={"token": "device-token-abc", "platform": "ios"},
            headers=auth_headers,
        )
    assert resp.status_code == 503


async def test_register_happy_path(client, auth_headers, _stub_db):
    from app.api.v1 import push as push_mod

    class _OkRepo:
        def __init__(self, _db): pass

        async def register(self, **_kwargs):
            return 42

    with patch.object(push_mod, "PushTokenRepository", _OkRepo):
        resp = await client.post(
            "/api/v1/push/tokens",
            json={"token": "device-token-abc", "platform": "ios"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == 42


async def test_revoke_404_when_token_unknown(client, auth_headers, _stub_db):
    from app.api.v1 import push as push_mod

    class _NoMatchRepo:
        def __init__(self, _db): pass

        async def unregister(self, _token):
            return False

    with patch.object(push_mod, "PushTokenRepository", _NoMatchRepo):
        resp = await client.delete(
            "/api/v1/push/tokens/unknown-token",
            headers=auth_headers,
        )
    assert resp.status_code == 404


async def test_revoke_happy_path(client, auth_headers, _stub_db):
    from app.api.v1 import push as push_mod

    class _OkRepo:
        def __init__(self, _db): pass

        async def unregister(self, _token):
            return True

    with patch.object(push_mod, "PushTokenRepository", _OkRepo):
        resp = await client.delete(
            "/api/v1/push/tokens/device-token-abc",
            headers=auth_headers,
        )
    assert resp.status_code == 200

"""T4-06 — installer download signed-URL endpoint."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-download")
os.environ.setdefault("INSTALLER_BASE_URL", "https://downloads.sentry.mn")

from app.services.installer_assets import (  # noqa: E402
    DOWNLOAD_TOKEN_TTL,
    InstallerDownloadPayload,
    issue_download_token,
    resolve_asset_url,
    sign_download_token,
    verify_download_token,
)
from app.services.installer_config import (  # noqa: E402
    InstallerTokenError,
)

SECRET = "test-secret-download"


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestResolveAssetUrl:
    @pytest.mark.parametrize("os_id,expected_suffix", [
        ("linux",   "/linux/install.sh"),
        ("windows", "/windows/SentryAgentSetup.exe"),
        ("macos",   "/macos/sentry-agent.pkg"),
    ])
    def test_default_layout(self, os_id, expected_suffix):
        url = resolve_asset_url(os_id, base_url="https://downloads.sentry.mn")
        assert url == f"https://downloads.sentry.mn{expected_suffix}"

    def test_base_url_trailing_slash_normalized(self):
        url = resolve_asset_url("linux", base_url="https://downloads.sentry.mn/")
        assert url == "https://downloads.sentry.mn/linux/install.sh"

    def test_overrides_take_priority(self):
        url = resolve_asset_url(
            "linux",
            base_url="https://x",
            overrides={"linux": "/custom/install.sh"},
        )
        assert url == "https://x/custom/install.sh"

    def test_unsupported_os_raises(self):
        with pytest.raises(ValueError, match="unsupported os"):
            resolve_asset_url("bsd", base_url="https://x")


class TestDownloadTokenRoundtrip:
    def _payload(self, *, os_id="linux", ttl_seconds=3600):
        return InstallerDownloadPayload(
            tenant_id="11111111-2222-3333-4444-555555555555",
            os=os_id,
            asset_url="https://downloads.sentry.mn/linux/install.sh",
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    def test_roundtrip(self):
        p = self._payload()
        token = sign_download_token(p, SECRET)
        decoded = verify_download_token(token, secret=SECRET)
        assert decoded.os == p.os
        assert decoded.asset_url == p.asset_url
        assert decoded.tenant_id == p.tenant_id

    def test_tamper_signature(self):
        token = sign_download_token(self._payload(), SECRET)
        head, tail = token.split(".", 1)
        mutated = tail[:-1] + ("A" if tail[-1] != "A" else "B")
        with pytest.raises(InstallerTokenError):
            verify_download_token(f"{head}.{mutated}", secret=SECRET)

    def test_wrong_secret(self):
        token = sign_download_token(self._payload(), "attacker")
        with pytest.raises(InstallerTokenError):
            verify_download_token(token, secret=SECRET)

    def test_expired(self):
        expired = InstallerDownloadPayload(
            tenant_id="t",
            os="linux",
            asset_url="https://x",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        token = sign_download_token(expired, SECRET)
        with pytest.raises(InstallerTokenError, match="expired"):
            verify_download_token(token, secret=SECRET)

    def test_malformed(self):
        with pytest.raises(InstallerTokenError):
            verify_download_token("garbage", secret=SECRET)

    def test_os_guard_rejects_forged_unknown_os(self):
        """A forged payload with an unsupported OS would pass signature
        if we signed it ourselves — we additionally reject on decode."""
        import base64, hashlib, hmac, json
        raw = {
            "v": 1,
            "t": "t",
            "o": "bsd",
            "u": "https://x",
            "e": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        }
        blob = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        head = base64.urlsafe_b64encode(blob).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(
            hmac.new(SECRET.encode(), head.encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        token = f"{head}.{sig}"
        with pytest.raises(InstallerTokenError, match="os"):
            verify_download_token(token, secret=SECRET)


class TestIssueDownloadToken:
    def test_ttl_defaults_to_24h(self):
        before = datetime.now(UTC)
        _, url, expires = issue_download_token(
            tenant_id="t", os="linux",
            base_url="https://downloads.sentry.mn",
            secret=SECRET,
        )
        assert url == "https://downloads.sentry.mn/linux/install.sh"
        delta = expires - before
        assert timedelta(hours=23, minutes=59) < delta <= DOWNLOAD_TOKEN_TTL + timedelta(seconds=2)


# ---------------------------------------------------------------------------
# Endpoint — GET /installer/download + GET /installer/download/{token}
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def scalar_one_or_none(self):
        return None


class _FakeDB:
    def __init__(self):
        self.audit_log_writes: list[dict] = []

    async def execute(self, query, params=None):
        text = str(query).lower()
        if "insert into audit_log" in text:
            self.audit_log_writes.append(dict(params or {}))
        return _FakeResult()

    async def commit(self):
        pass


@pytest.fixture
def fake_app():
    from app.api.v1.installer import router  # noqa: PLC0415
    from app.core.tenant_auth import get_current_tenant  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/installer")

    db = _FakeDB()

    async def _db_override():
        yield db

    async def _tenant_override():
        return {
            "tenant_id": "11111111-2222-3333-4444-555555555555",
            "status": "active",
            "plan": "pro",
        }

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_tenant] = _tenant_override
    return app, db


def test_issue_download_url_writes_audit_log(fake_app):
    from fastapi.testclient import TestClient

    app, db = fake_app
    client = TestClient(app)

    resp = client.get("/api/v1/installer/download?os=linux")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["os"] == "linux"
    assert "/api/v1/installer/download/" in body["download_url"]

    # Audit log entry written exactly once, with the right action + OS.
    assert len(db.audit_log_writes) == 1
    entry = db.audit_log_writes[0]
    assert entry["action"] == "installer_download_issued"
    assert "linux" in entry["details"]


@pytest.mark.parametrize("os_id", ["linux", "windows", "macos"])
def test_issue_supports_all_os(fake_app, os_id):
    from fastapi.testclient import TestClient
    app, _db = fake_app
    resp = TestClient(app).get(f"/api/v1/installer/download?os={os_id}")
    assert resp.status_code == 200


def test_issue_rejects_unsupported_os(fake_app):
    from fastapi.testclient import TestClient
    app, _db = fake_app
    resp = TestClient(app).get("/api/v1/installer/download?os=bsd")
    # 422 — Literal-typed query param rejects the string.
    assert resp.status_code == 422


def test_follow_redirects_to_cdn(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    issued = client.get("/api/v1/installer/download?os=windows").json()
    token = issued["download_url"].rsplit("/", 1)[-1]

    resp = client.get(
        f"/api/v1/installer/download/{token}",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/windows/SentryAgentSetup.exe")


def test_follow_invalid_token_returns_410(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    resp = client.get(
        "/api/v1/installer/download/garbage.notatoken",
        follow_redirects=False,
    )
    assert resp.status_code == 410


def test_follow_expired_token_returns_410(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    expired = InstallerDownloadPayload(
        tenant_id="t",
        os="linux",
        asset_url="https://downloads.sentry.mn/linux/install.sh",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    token = sign_download_token(expired, SECRET)
    resp = client.get(
        f"/api/v1/installer/download/{token}",
        follow_redirects=False,
    )
    assert resp.status_code == 410

"""T4-02 — installer config signed-URL download.

Two layers of coverage:

1. Pure logic in `app.services.installer_config` — YAML shape,
   token sign/verify roundtrip, tamper + expiry detection.
2. Endpoint behavior — POST rotates + returns URL, GET decodes +
   streams YAML, error paths surface 410.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT_DIR = ROOT / "shoplift_detector"
if str(SHOPLIFT_DIR) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT_DIR))

os.environ.setdefault("SECRET_KEY", "test-secret-key-installer-pytest")
os.environ.setdefault("PUBLIC_BASE_URL", "https://api.sentry.mn")

from shoplift_detector.app.services.installer_config import (  # noqa: E402
    INSTALLER_TOKEN_TTL,
    TOKEN_VERSION,
    InstallerTokenError,
    InstallerTokenPayload,
    build_config_yaml,
    build_download_url,
    issue_installer_token,
    sign_download_token,
    verify_download_token,
)

SECRET = "test-secret-key-installer-pytest"


# ---------------------------------------------------------------------------
# build_config_yaml
# ---------------------------------------------------------------------------

class TestBuildConfigYaml:
    def test_contains_all_required_fields(self):
        yaml = build_config_yaml(
            tenant_id="11111111-2222-3333-4444-555555555555",
            api_key="sk_live_example_key_value_here",
            server_url="https://api.sentry.mn",
        )
        assert 'server_url: "https://api.sentry.mn"' in yaml
        assert 'tenant_id: "11111111-2222-3333-4444-555555555555"' in yaml
        assert 'api_key: "sk_live_example_key_value_here"' in yaml
        assert "heartbeat_interval_s: 60" in yaml

    def test_server_url_trailing_slash_stripped(self):
        """Agent joins paths by concatenation — if the configured
        origin has a trailing slash we get `//alerts` calls. Normalize
        at render time."""
        yaml = build_config_yaml(
            tenant_id="t", api_key="k", server_url="https://api.sentry.mn/"
        )
        assert 'server_url: "https://api.sentry.mn"' in yaml
        assert "api.sentry.mn/" not in yaml.split("server_url")[1].splitlines()[0][:-1]

    def test_custom_heartbeat_rendered_as_integer(self):
        yaml = build_config_yaml(
            tenant_id="t", api_key="k", server_url="https://x", heartbeat_interval_s=120
        )
        assert "heartbeat_interval_s: 120" in yaml

    @pytest.mark.parametrize("bad", ['line1\nline2', 'contains"quote'])
    def test_rejects_illegal_chars(self, bad):
        """A YAML-unsafe character (newline, double-quote) would let
        a malicious tenant inject arbitrary config. Block at render."""
        with pytest.raises(ValueError):
            build_config_yaml(
                tenant_id=bad, api_key="k", server_url="https://x"
            )


# ---------------------------------------------------------------------------
# Token sign / verify
# ---------------------------------------------------------------------------

def _make_payload(expires_at: datetime | None = None) -> InstallerTokenPayload:
    return InstallerTokenPayload(
        tenant_id="11111111-2222-3333-4444-555555555555",
        api_key="sk_live_testroundtrip_abcdef",
        server_url="https://api.sentry.mn",
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
    )


class TestTokenSignVerify:
    def test_token_roundtrip(self):
        original = _make_payload()
        token = sign_download_token(original, SECRET)
        decoded = verify_download_token(token, secret=SECRET)
        assert decoded.tenant_id == original.tenant_id
        assert decoded.api_key == original.api_key
        assert decoded.server_url == original.server_url
        # Second precision is fine — we serialize to unix ts.
        assert int(decoded.expires_at.timestamp()) == int(
            original.expires_at.timestamp()
        )

    def test_token_format_has_two_segments(self):
        token = sign_download_token(_make_payload(), SECRET)
        assert token.count(".") == 1
        head, tail = token.split(".", 1)
        assert head and tail

    def test_tampered_payload_rejected(self):
        """Flip a byte inside the payload segment — signature must
        stop matching."""
        token = sign_download_token(_make_payload(), SECRET)
        head, tail = token.split(".", 1)
        # Mutate a character deterministically.
        mutated = head[:-1] + ("A" if head[-1] != "A" else "B")
        with pytest.raises(InstallerTokenError):
            verify_download_token(f"{mutated}.{tail}", secret=SECRET)

    def test_tampered_signature_rejected(self):
        token = sign_download_token(_make_payload(), SECRET)
        head, tail = token.split(".", 1)
        mutated = tail[:-1] + ("A" if tail[-1] != "A" else "B")
        with pytest.raises(InstallerTokenError):
            verify_download_token(f"{head}.{mutated}", secret=SECRET)

    def test_signature_verified_against_secret(self):
        """A valid token signed with a different secret must not
        decode under the original."""
        token = sign_download_token(_make_payload(), "attacker-secret")
        with pytest.raises(InstallerTokenError):
            verify_download_token(token, secret=SECRET)

    def test_expired_token_rejected(self):
        expired = _make_payload(
            expires_at=datetime.now(UTC) - timedelta(seconds=1)
        )
        token = sign_download_token(expired, SECRET)
        with pytest.raises(InstallerTokenError, match="expired"):
            verify_download_token(token, secret=SECRET)

    def test_future_token_accepted_under_fixed_now(self):
        payload = _make_payload(
            expires_at=datetime(2030, 1, 1, tzinfo=UTC)
        )
        token = sign_download_token(payload, SECRET)
        decoded = verify_download_token(
            token,
            secret=SECRET,
            now=datetime(2029, 12, 31, tzinfo=UTC),
        )
        assert decoded.api_key == payload.api_key

    @pytest.mark.parametrize("bad", [
        "",
        "not-a-token",
        "onlyonedotted.",
        ".",
        "a.b.c",
    ])
    def test_malformed_tokens_rejected(self, bad):
        with pytest.raises(InstallerTokenError):
            verify_download_token(bad, secret=SECRET)

    def test_wrong_version_rejected(self):
        """Future schema migrations must invalidate old tokens."""
        payload = _make_payload()
        tampered_dict = payload.to_dict() | {"v": TOKEN_VERSION + 99}
        # Manually sign a mutated payload so we exercise the
        # version guard, not the signature guard.
        payload_json = json.dumps(
            tampered_dict, sort_keys=True, separators=(",", ":")
        ).encode()
        payload_b64 = (
            base64.urlsafe_b64encode(payload_json).rstrip(b"=").decode()
        )
        import hashlib
        import hmac
        sig = hmac.new(
            SECRET.encode(), payload_b64.encode(), hashlib.sha256
        ).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
        token = f"{payload_b64}.{sig_b64}"
        with pytest.raises(InstallerTokenError, match="version"):
            verify_download_token(token, secret=SECRET)


# ---------------------------------------------------------------------------
# issue_installer_token — convenience wrapper
# ---------------------------------------------------------------------------

class TestIssueInstallerToken:
    def test_ttl_is_24h_by_default(self):
        before = datetime.now(UTC)
        token, expires_at = issue_installer_token(
            tenant_id="t",
            api_key="k",
            server_url="https://x",
            secret=SECRET,
        )
        # Token must round-trip.
        decoded = verify_download_token(token, secret=SECRET)
        assert decoded.tenant_id == "t"
        # TTL window is 24h within a few seconds of wall clock.
        delta = expires_at - before
        assert timedelta(hours=23, minutes=59) < delta <= INSTALLER_TOKEN_TTL + timedelta(
            seconds=2
        )

    def test_custom_ttl(self):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        _, expires_at = issue_installer_token(
            tenant_id="t",
            api_key="k",
            server_url="https://x",
            secret=SECRET,
            now=now,
            ttl=timedelta(minutes=5),
        )
        assert expires_at == now + timedelta(minutes=5)


# ---------------------------------------------------------------------------
# build_download_url
# ---------------------------------------------------------------------------

class TestBuildDownloadUrl:
    def test_url_shape(self):
        token = "abc.def"
        assert (
            build_download_url(base_url="https://api.sentry.mn", token=token)
            == "https://api.sentry.mn/api/v1/installer/config/abc.def"
        )

    def test_trailing_slash_stripped(self):
        assert (
            build_download_url(base_url="https://api.sentry.mn/", token="t.s")
            == "https://api.sentry.mn/api/v1/installer/config/t.s"
        )


# ---------------------------------------------------------------------------
# Endpoint wiring — lightweight FastAPI test using TestClient
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, row=None, scalar=None):
        self._row = row
        self._scalar = scalar

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    """Async DB stand-in that records executed SQL + supplies row data."""

    def __init__(self):
        self.tenant_row = {
            "tenant_id": "11111111-2222-3333-4444-555555555555",
            "legal_name": "Demo LLC",
            "display_name": "Demo",
            "email": "demo@sentry.mn",
            "phone": None,
            "status": "active",
            "plan": "pro",
            "created_at": None,
            "trial_ends_at": None,
            "current_period_end": None,
            "payment_method_id": None,
            "previous_api_key_expires_at": datetime(
                2030, 1, 1, tzinfo=UTC
            ),
            "resource_quota": {"max_cameras": 50},
        }
        self.queries: list[str] = []

    async def execute(self, query, params=None):
        self.queries.append(str(query))
        text = str(query).lower()
        if "update tenants" in text:
            return _FakeResult()
        if "select tenant_id" in text and "organization_tenant_map" in text:
            return _FakeResult(scalar=None)
        if "from tenants" in text:
            return _FakeResult(row=self.tenant_row)
        return _FakeResult()

    async def commit(self):
        pass


@pytest.fixture
def fake_app():
    """Minimal FastAPI app that only mounts the installer router and
    overrides the tenant + DB dependencies so we don't need Postgres.

    IMPORTANT: the override keys must be the *same module-level
    callable objects* the router imports. Because `SHOPLIFT_DIR` is
    on `sys.path`, the router resolves `app.core.tenant_auth.*`;
    importing via the `shoplift_detector.app.*` alias here would
    create a separate module instance and the override would silently
    miss.
    """
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
            "plan": "pro",
            "status": "active",
        }

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_tenant] = _tenant_override
    return app, db


def test_post_config_returns_signed_download_url(fake_app):
    from fastapi.testclient import TestClient

    app, db = fake_app
    client = TestClient(app)

    resp = client.post("/api/v1/installer/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["download_url"].startswith(
        "https://api.sentry.mn/api/v1/installer/config/"
    )
    assert body["expires_at"]
    assert body["previous_api_key_valid_until"].startswith("2030-01-01")
    # Rotation happened — an UPDATE on tenants ran.
    assert any("update tenants" in q.lower() for q in db.queries)


def test_get_config_streams_yaml_with_attachment_headers(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    post = client.post("/api/v1/installer/config").json()
    download_url = post["download_url"]
    # Strip scheme+host so TestClient resolves against the app.
    path = download_url.split("https://api.sentry.mn", 1)[1]

    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/x-yaml")
    assert 'attachment; filename="config.yaml"' in resp.headers[
        "content-disposition"
    ]
    assert resp.headers["cache-control"] == "no-store"

    yaml_body = resp.text
    assert "tenant_id:" in yaml_body
    assert "api_key:" in yaml_body
    assert 'server_url: "https://api.sentry.mn"' in yaml_body


def test_get_config_invalid_token_returns_410(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    resp = client.get("/api/v1/installer/config/garbage.notatoken")
    # 410 Gone — single error surface regardless of failure reason.
    assert resp.status_code == 410
    assert "хугацаа" in resp.json()["detail"].lower() or "invalid" in resp.json()[
        "detail"
    ].lower()


def test_get_config_expired_token_returns_410(fake_app):
    from fastapi.testclient import TestClient

    app, _db = fake_app
    client = TestClient(app)

    expired_token, _ = issue_installer_token(
        tenant_id="11111111-2222-3333-4444-555555555555",
        api_key="sk_live_x",
        server_url="https://api.sentry.mn",
        secret=SECRET,
        now=datetime(2020, 1, 1, tzinfo=UTC),
        ttl=timedelta(seconds=1),
    )
    resp = client.get(f"/api/v1/installer/config/{expired_token}")
    assert resp.status_code == 410

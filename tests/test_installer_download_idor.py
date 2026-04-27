"""Cross-tenant IDOR — installer download + config endpoints (T4-02 / T4-06).

The installer flow embeds a tenant's raw API key into a signed URL so
an agent can bootstrap without an interactive login. That design makes
URL secrecy the only line of defense. These tests pin what the server
is allowed to infer from a presented token — specifically, it must not
let tenant B use a tenant A-signed token to act as tenant A, and the
backend must never commingle two tenants' audit/rotation state.

Complements `test_cross_tenant_idor_pen.py` (bearer/API-key surface)
and `test_installer_download.py` (happy path + signature tamper).
"""

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

os.environ.setdefault("SECRET_KEY", "test-secret-idor")
os.environ.setdefault("INSTALLER_BASE_URL", "https://downloads.sentry.mn")

from app.core.config import settings  # noqa: E402
from app.services.installer_assets import (  # noqa: E402
    InstallerDownloadPayload,
    issue_download_token,
    sign_download_token,
    verify_download_token,
)
from app.services.installer_config import (  # noqa: E402
    InstallerTokenError,
    issue_installer_token,
    verify_download_token as verify_config_token,
)

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
# The FastAPI endpoint signs with settings.SECRET_KEY (read from env at
# import time); our pure-logic tests sign with the same secret so both
# paths agree regardless of which env var won the conftest race.
SECRET = settings.SECRET_KEY


# ---------------------------------------------------------------------------
# Token-format confusion — download vs config tokens are not interchangeable
# ---------------------------------------------------------------------------

def test_download_token_cannot_be_verified_as_config_token():
    """A token signed for the installer-download endpoint must not
    decode as a config token. Payload shapes differ (`u` asset_url vs
    `k` api_key) and the verifier enforces that."""
    token, _asset_url, _expires = issue_download_token(
        tenant_id=TENANT_A,
        os="linux",
        base_url="https://downloads.sentry.mn",
        secret=SECRET,
    )
    with pytest.raises(InstallerTokenError):
        verify_config_token(token, secret=SECRET)


def test_config_token_cannot_be_verified_as_download_token():
    """Inverse: config token (carries `api_key`) must not pass the
    download verifier (which expects an asset_url)."""
    token, _expires = issue_installer_token(
        tenant_id=TENANT_A,
        api_key="sk_live_" + "x" * 40,
        server_url="https://api.sentry.mn",
        secret=SECRET,
    )
    with pytest.raises(InstallerTokenError):
        verify_download_token(token, secret=SECRET)


# ---------------------------------------------------------------------------
# Tenant-ID binding — a signed token carries its tenant and survives roundtrip
# ---------------------------------------------------------------------------

def test_download_token_preserves_tenant_identity():
    """The signed payload carries the issuing tenant_id. A downstream
    audit step relying on the token cannot confuse A for B."""
    token_a, _url, _exp = issue_download_token(
        tenant_id=TENANT_A,
        os="linux",
        base_url="https://downloads.sentry.mn",
        secret=SECRET,
    )
    token_b, _url, _exp = issue_download_token(
        tenant_id=TENANT_B,
        os="linux",
        base_url="https://downloads.sentry.mn",
        secret=SECRET,
    )
    decoded_a = verify_download_token(token_a, secret=SECRET)
    decoded_b = verify_download_token(token_b, secret=SECRET)
    assert decoded_a.tenant_id == TENANT_A
    assert decoded_b.tenant_id == TENANT_B
    assert decoded_a.tenant_id != decoded_b.tenant_id


def test_tenant_b_cannot_re_sign_tenant_a_payload_with_own_secret():
    """If tenant B somehow learned tenant A's download URL and tried
    to re-sign it with a different secret, verification fails. Proves
    the SECRET_KEY is load-bearing, not cosmetic."""
    payload = InstallerDownloadPayload(
        tenant_id=TENANT_A,
        os="linux",
        asset_url="https://downloads.sentry.mn/linux/install.sh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    forged = sign_download_token(payload, secret="different-secret")
    with pytest.raises(InstallerTokenError):
        verify_download_token(forged, secret=SECRET)


# ---------------------------------------------------------------------------
# Endpoint-level — bearer A cannot emit an audit log scoped to tenant B
# ---------------------------------------------------------------------------

class _FakeResult:
    def mappings(self):
        return self

    def fetchone(self):
        return None

    def scalar_one_or_none(self):
        return None


class _CapturingDB:
    def __init__(self):
        self.audit_writes: list[dict] = []

    async def execute(self, query, params=None):
        text = str(query).lower()
        if "insert into audit_log" in text:
            self.audit_writes.append(dict(params or {}))
        return _FakeResult()

    async def commit(self):
        pass


@pytest.fixture
def tenant_app():
    """Builds a FastAPI app with overridable tenant identity — flip
    the fixture's returned setter to swap which tenant the bearer auth
    resolves to."""
    from app.api.v1.installer import router  # noqa: PLC0415
    from app.core.rate_limiting import limiter  # noqa: PLC0415
    from app.core.tenant_auth import get_current_tenant  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415

    # Tests share a single TestClient IP — the production-tuned
    # 5/minute INSTALLER_ISSUE limit would block the 3rd test in this
    # file's run. Disable the limiter for the duration of this fixture
    # so we measure correctness, not cumulative request count.
    previously_enabled = limiter.enabled
    limiter.enabled = False

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/installer")

    db = _CapturingDB()

    async def _db_override():
        yield db

    state = {"tenant_id": TENANT_A}

    async def _tenant_override():
        return {"tenant_id": state["tenant_id"], "status": "active", "plan": "pro"}

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_tenant] = _tenant_override

    def _set_tenant(tid: str):
        state["tenant_id"] = tid

    try:
        yield app, db, _set_tenant
    finally:
        limiter.enabled = previously_enabled


def test_audit_log_is_scoped_to_authenticated_tenant(tenant_app):
    """Two successive calls, one per tenant. Each audit row must
    reference only its own tenant_id — no cross-contamination."""
    from fastapi.testclient import TestClient

    app, db, set_tenant = tenant_app
    client = TestClient(app)

    set_tenant(TENANT_A)
    resp_a = client.get("/api/v1/installer/download?os=linux")
    assert resp_a.status_code == 200

    set_tenant(TENANT_B)
    resp_b = client.get("/api/v1/installer/download?os=linux")
    assert resp_b.status_code == 200

    assert len(db.audit_writes) == 2
    assert db.audit_writes[0]["resource_uuid"] == TENANT_A
    assert db.audit_writes[1]["resource_uuid"] == TENANT_B
    # Belt-and-braces: the two rows must not share a uuid.
    assert db.audit_writes[0]["resource_uuid"] != db.audit_writes[1]["resource_uuid"]


def test_bearer_tenant_a_cannot_forge_tenant_b_download_url(tenant_app):
    """An attacker cannot bounce through the download-issuance
    endpoint to obtain a URL bound to someone else's tenant_id — the
    endpoint ignores request-supplied tenant and uses the bearer's."""
    from fastapi.testclient import TestClient

    app, _db, set_tenant = tenant_app
    client = TestClient(app)

    set_tenant(TENANT_A)
    resp = client.get("/api/v1/installer/download?os=linux")
    body = resp.json()

    # The URL's trailing token decodes to tenant A — never B — regardless
    # of any body params (there are none) the attacker could smuggle.
    token = body["download_url"].rsplit("/", 1)[-1]
    decoded = verify_download_token(token, secret=SECRET)
    assert decoded.tenant_id == TENANT_A
    assert decoded.tenant_id != TENANT_B


def test_expired_token_rejected_even_with_valid_tenant(tenant_app):
    """Timing window matters: an expired token for the right tenant
    still gets 410. Ensures no 'tenant is active, let it through'
    shortcut."""
    from fastapi.testclient import TestClient

    app, _db, _set = tenant_app
    client = TestClient(app)

    expired = InstallerDownloadPayload(
        tenant_id=TENANT_A,
        os="linux",
        asset_url="https://downloads.sentry.mn/linux/install.sh",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    token = sign_download_token(expired, SECRET)
    resp = client.get(f"/api/v1/installer/download/{token}", follow_redirects=False)
    assert resp.status_code == 410

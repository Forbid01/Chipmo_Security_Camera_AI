"""Installer binary download URLs (T4-06).

Separate from `installer_config` — *that* module signs a YAML blob
for on-premise consumption, *this* module signs a short-lived
redirect to the public installer binary. Kept side-by-side because
both use the same HMAC scheme, just with different payload shapes.

The download URL is a two-step handshake:

1. POST/GET the authenticated endpoint with `?os=linux|windows|macos`.
   The backend resolves the actual CDN URL, signs a token that binds
   the OS + tenant + expiry, and audit-logs the issuance.
2. The returned `/api/v1/installer/download/{token}` URL is fetched
   unauthenticated by the installer client — the backend verifies
   the signature and 302-redirects to the real asset.

Rationale for the 2-step: the CDN-hosted installer is public (no
customer secrets baked in), but we want per-tenant audit trails +
a single choke point for rate-limiting.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.installer_config import InstallerTokenError

SUPPORTED_OS = frozenset({"linux", "windows", "macos"})

DOWNLOAD_TOKEN_TTL = timedelta(hours=24)
DOWNLOAD_TOKEN_VERSION = 1

# Default CDN layout. Override per-env via `settings.INSTALLER_BASE_URL`
# + `INSTALLER_ASSET_PATHS`. The paths deliberately match the layout
# of the release-asset upload steps in the CI workflows (T4-03 / T4-04
# attach these files to a GitHub release).
DEFAULT_ASSET_PATHS: dict[str, str] = {
    "linux":   "/linux/install.sh",
    "windows": "/windows/SentryAgentSetup.exe",
    "macos":   "/macos/sentry-agent.pkg",
}


@dataclass(frozen=True)
class InstallerDownloadPayload:
    tenant_id: str
    os: str
    asset_url: str
    expires_at: datetime
    version: int = DOWNLOAD_TOKEN_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.version,
            "t": self.tenant_id,
            "o": self.os,
            "u": self.asset_url,
            "e": int(self.expires_at.timestamp()),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> InstallerDownloadPayload:
        for required in ("v", "t", "o", "u", "e"):
            if required not in raw:
                raise InstallerTokenError(f"missing field: {required}")
        return cls(
            tenant_id=str(raw["t"]),
            os=str(raw["o"]),
            asset_url=str(raw["u"]),
            expires_at=datetime.fromtimestamp(int(raw["e"]), tz=UTC),
            version=int(raw["v"]),
        )


def resolve_asset_url(
    os: str,
    *,
    base_url: str,
    overrides: dict[str, str] | None = None,
) -> str:
    """Map an OS selector to its public CDN URL.

    Raises `ValueError` on unknown OS — the handler returns 400. We
    explicitly enumerate supported OSes so a typo in a query string
    doesn't silently build a broken URL.
    """
    if os not in SUPPORTED_OS:
        raise ValueError(
            f"unsupported os {os!r}; expected one of {sorted(SUPPORTED_OS)}"
        )
    paths = DEFAULT_ASSET_PATHS if overrides is None else {**DEFAULT_ASSET_PATHS, **overrides}
    return f"{base_url.rstrip('/')}{paths[os]}"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + pad)
    except (ValueError, TypeError) as exc:
        raise InstallerTokenError("malformed base64") from exc


def _sign(payload_b64: str, secret: str) -> str:
    mac = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    )
    return _b64url_encode(mac.digest())


def sign_download_token(
    payload: InstallerDownloadPayload, secret: str
) -> str:
    payload_json = json.dumps(
        payload.to_dict(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    return f"{payload_b64}.{_sign(payload_b64, secret)}"


def verify_download_token(
    token: str, *, secret: str, now: datetime | None = None
) -> InstallerDownloadPayload:
    if not isinstance(token, str) or token.count(".") != 1:
        raise InstallerTokenError("token shape")
    payload_b64, signature_b64 = token.split(".", 1)
    if not hmac.compare_digest(_sign(payload_b64, secret), signature_b64):
        raise InstallerTokenError("signature mismatch")
    try:
        raw = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallerTokenError("payload decode") from exc
    if not isinstance(raw, dict):
        raise InstallerTokenError("payload shape")

    payload = InstallerDownloadPayload.from_dict(raw)
    if payload.version != DOWNLOAD_TOKEN_VERSION:
        raise InstallerTokenError("token version")
    if payload.os not in SUPPORTED_OS:
        raise InstallerTokenError("os")

    now = now or datetime.now(UTC)
    if payload.expires_at <= now:
        raise InstallerTokenError("token expired")
    return payload


def issue_download_token(
    *,
    tenant_id: str,
    os: str,
    base_url: str,
    secret: str,
    overrides: dict[str, str] | None = None,
    now: datetime | None = None,
    ttl: timedelta = DOWNLOAD_TOKEN_TTL,
) -> tuple[str, str, datetime]:
    """Bundle resolve + sign. Returns (token, asset_url, expires_at).

    The asset_url is surfaced to the audit log alongside the token
    so the compliance trail has everything needed to identify what
    was downloaded without peeking into a signed blob.
    """
    asset_url = resolve_asset_url(os, base_url=base_url, overrides=overrides)
    now = now or datetime.now(UTC)
    expires_at = now + ttl
    payload = InstallerDownloadPayload(
        tenant_id=tenant_id,
        os=os,
        asset_url=asset_url,
        expires_at=expires_at,
    )
    return sign_download_token(payload, secret), asset_url, expires_at


__all__ = [
    "DEFAULT_ASSET_PATHS",
    "DOWNLOAD_TOKEN_TTL",
    "DOWNLOAD_TOKEN_VERSION",
    "InstallerDownloadPayload",
    "SUPPORTED_OS",
    "issue_download_token",
    "resolve_asset_url",
    "sign_download_token",
    "verify_download_token",
]

"""Installer config endpoints — T4-02.

Two endpoints:

* `POST /api/v1/installer/config` (authenticated tenant):
    Rotates the tenant's API key and returns a 24-hour signed
    download URL. The raw key is embedded only in the URL — the
    server does not persist it anywhere after this call returns.

* `GET /api/v1/installer/config/{token}` (unauthenticated, token-signed):
    Decodes the signed token, rebuilds the agent YAML, and streams
    it as a file attachment. Fails with 410 Gone for any token
    verification issue so attackers can't distinguish expired from
    tampered.
"""

from __future__ import annotations

from typing import Literal

from app.core.config import settings
from app.core.rate_limiting import RateLimits, limiter
from app.core.tenant_auth import CurrentTenant
from app.db.repository.audit_log import AuditLogRepository
from app.db.repository.tenants import TenantRepository
from app.db.session import DB
from app.schemas.installer import (
    InstallerConfigUrlResponse,
    InstallerDownloadResponse,
)
from app.services.api_key_service import rotate_api_key
from app.services.installer_assets import (
    issue_download_token,
    verify_download_token as verify_asset_token,
)
from app.services.installer_config import (
    InstallerTokenError,
    build_config_yaml,
    build_download_url,
    issue_installer_token,
    verify_download_token,
)
from app.services.onboarding_events import (
    INSTALLER_DOWNLOADED,
    broker,
    make_event,
)
from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, RedirectResponse

router = APIRouter()


def _resolve_server_url() -> str:
    """Which origin to embed in the downloaded config.

    Prefer `PUBLIC_BASE_URL` so dev/staging/prod can differ, but fall
    back to the production hostname when ops hasn't wired it yet.
    """
    configured = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    return configured or "https://api.sentry.mn"


@router.post(
    "/config",
    response_model=InstallerConfigUrlResponse,
    summary="Rotate API key and issue a 24h installer-config URL",
)
@limiter.limit(RateLimits.INSTALLER_ISSUE)
async def create_installer_config_url(
    request: Request,
    response: Response,
    db: DB,
    tenant: CurrentTenant,
) -> InstallerConfigUrlResponse:
    repo = TenantRepository(db)
    tenant_id = str(tenant["tenant_id"])

    issued = await rotate_api_key(repo, tenant_id=tenant_id)

    server_url = _resolve_server_url()
    token, expires_at = issue_installer_token(
        tenant_id=tenant_id,
        api_key=issued.raw,
        server_url=server_url,
        secret=settings.SECRET_KEY,
    )
    download_url = build_download_url(base_url=server_url, token=token)

    # Re-read the row so the response carries the exact rotation
    # cutoff that was persisted, not a guess from the service clock.
    refreshed = await repo.get_by_id(tenant_id)
    prev_valid_until = (
        refreshed.get("previous_api_key_expires_at") if refreshed else None
    )

    return InstallerConfigUrlResponse(
        download_url=download_url,
        expires_at=expires_at.isoformat(),
        previous_api_key_valid_until=(
            prev_valid_until.isoformat() if prev_valid_until else ""
        ),
    )


@router.get(
    "/download",
    response_model=InstallerDownloadResponse,
    summary="Issue a 24h-signed installer-download URL (T4-06)",
)
@limiter.limit(RateLimits.INSTALLER_ISSUE)
async def create_installer_download_url(
    request: Request,
    response: Response,
    db: DB,
    tenant: CurrentTenant,
    os: Literal["linux", "windows", "macos"] = Query(
        ...,
        description="Target OS for the installer binary.",
    ),
) -> InstallerDownloadResponse:
    tenant_id = str(tenant["tenant_id"])

    try:
        token, asset_url, expires_at = issue_download_token(
            tenant_id=tenant_id,
            os=os,
            base_url=settings.INSTALLER_BASE_URL,
            secret=settings.SECRET_KEY,
        )
    except ValueError as exc:
        # Pydantic caught the enum; ValueError here means the resolver
        # rejected a supported-looking OS (shouldn't happen).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    public_base = (settings.PUBLIC_BASE_URL or "").rstrip("/") or (
        str(request.base_url).rstrip("/")
    )
    download_url = f"{public_base}/api/v1/installer/download/{token}"

    # Audit log — compliance trail for who requested which installer.
    # IP + user-agent captured for forensics if a leaked URL is abused.
    audit_repo = AuditLogRepository(db)
    await audit_repo.log(
        action="installer_download_issued",
        resource_type="tenant",
        resource_uuid=tenant_id,
        details={"os": os, "asset_url": asset_url},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()

    await broker.publish(
        tenant_id,
        make_event(INSTALLER_DOWNLOADED, payload={"os": os}),
    )

    return InstallerDownloadResponse(
        download_url=download_url,
        os=os,
        expires_at=expires_at.isoformat(),
    )


@router.get(
    "/download/{token}",
    summary="302 redirect to the installer binary on the CDN",
)
@limiter.limit(RateLimits.INSTALLER_REDEEM)
async def follow_installer_download(
    request: Request,
    token: str = Path(..., min_length=16, max_length=4096),
) -> RedirectResponse:
    try:
        payload = verify_asset_token(token, secret=settings.SECRET_KEY)
    except InstallerTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Энэ URL-ийн хугацаа дууссан эсвэл хүчингүй.",
        ) from exc
    return RedirectResponse(url=payload.asset_url, status_code=302)


@router.get(
    "/config/{token}",
    response_class=PlainTextResponse,
    summary="Download a 24h-signed agent config.yaml",
)
@limiter.limit(RateLimits.INSTALLER_REDEEM)
async def download_installer_config(
    request: Request,
    token: str = Path(..., min_length=16, max_length=4096),
) -> PlainTextResponse:
    try:
        payload = verify_download_token(token, secret=settings.SECRET_KEY)
    except InstallerTokenError as exc:
        # 410 Gone is the right signal for "this URL is no longer
        # valid" — installers can distinguish it from 401/403 paths
        # that might be retried with fresh auth.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Энэ URL-ийн хугацаа дууссан эсвэл хүчингүй.",
        ) from exc

    body = build_config_yaml(
        tenant_id=payload.tenant_id,
        api_key=payload.api_key,
        server_url=payload.server_url,
    )
    return PlainTextResponse(
        content=body,
        media_type="application/x-yaml; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="config.yaml"',
            "Cache-Control": "no-store",
        },
    )

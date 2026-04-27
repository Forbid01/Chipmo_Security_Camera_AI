"""Pydantic response schemas for installer endpoints (T4-02 / T4-06)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InstallerConfigUrlResponse(BaseModel):
    """Returned by POST /api/v1/installer/config.

    The raw API key has already been rotated and embedded in the
    signed `download_url` — clients must fetch the URL within the
    TTL or call this endpoint again to rotate+regenerate.
    """

    download_url: str = Field(
        ..., description="24-hour signed URL that streams config.yaml"
    )
    expires_at: str = Field(
        ..., description="ISO-8601 timestamp when the URL stops working"
    )
    previous_api_key_valid_until: str = Field(
        ...,
        description=(
            "ISO-8601 when the pre-rotation key stops accepting "
            "requests — existing deployed agents keep working until "
            "this moment."
        ),
    )
    message: str = Field(
        default=(
            "Татаж авсан config.yaml-д шинэ API key шингэсэн байгаа. "
            "24 цагийн дотор агентдаа суулгана уу — хугацаа нь өнгөрвөл "
            "шинэ URL үүсгэнэ."
        ),
        description="User-facing Mongolian guidance",
    )


class InstallerDownloadResponse(BaseModel):
    """Returned by GET /api/v1/installer/download (T4-06).

    Unlike the config-URL flow, the binary itself is public — this
    URL is a thin tenant-scoped + audit-logged redirect. Re-requesting
    before the 24h TTL elapses is fine; a new token is minted and the
    old one remains valid until its expiry.
    """

    download_url: str = Field(
        ..., description="24-hour signed redirect URL to the installer binary"
    )
    os: Literal["linux", "windows", "macos"]
    expires_at: str = Field(
        ..., description="ISO-8601 timestamp when the redirect stops working"
    )

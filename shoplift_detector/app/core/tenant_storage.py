"""Per-tenant object storage layout (T1-13, DOC-05 §3.5).

Every tenant's clips / snapshots / exports live under a dedicated
prefix inside the shared MinIO bucket:

    <bucket>/
        tenant_{uuid}/
            store_{id}/
                YYYY-MM-DD/
                    event_{event_id}.mp4

The layout is stable so the purge cron (T1-11) can wipe a whole
tenant by deleting the `tenant_{uuid}/` prefix and IAM policies can
scope a tenant's API key to paths matching the prefix.

This module owns path construction only — the actual upload/delete
happens through the existing `app.services.storage` abstraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.core.tenant_keys import _canonicalize

# Event id / filename sanitation — keep paths portable across
# S3 / MinIO / local disk and prevent path traversal. Accept
# alphanumerics, `.-_`, nothing else.
_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]")


def _safe_segment(value: str) -> str:
    cleaned = _SAFE_SEGMENT.sub("_", value)
    if not cleaned or cleaned in ("", ".", ".."):
        raise ValueError(f"unsafe storage segment: {value!r}")
    return cleaned


@dataclass(frozen=True)
class TenantBucketLayout:
    """Produces the object keys for one tenant.

    Usage:
        layout = TenantBucketLayout(tenant_id=tenant["tenant_id"])
        key = layout.event_clip(store_id=1, event_id="abc", ext="mp4")
        # -> tenant_{uuid}/store_1/2026-04-22/event_abc.mp4
    """

    tenant_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _canonicalize(self.tenant_id))

    # ------------------------------------------------------------------
    # Prefixes
    # ------------------------------------------------------------------

    @property
    def tenant_prefix(self) -> str:
        """`tenant_{uuid}/` — IAM policy anchor + purge root."""
        return f"tenant_{self.tenant_id}/"

    def store_prefix(self, store_id: int) -> str:
        return f"{self.tenant_prefix}store_{store_id}/"

    def day_prefix(self, store_id: int, when: date | datetime) -> str:
        if isinstance(when, datetime):
            when = when.date()
        return f"{self.store_prefix(store_id)}{when.isoformat()}/"

    # ------------------------------------------------------------------
    # File keys
    # ------------------------------------------------------------------

    def event_clip(
        self,
        *,
        store_id: int,
        event_id: str,
        when: date | datetime | None = None,
        ext: str = "mp4",
    ) -> str:
        day = when if when is not None else datetime.now(UTC).date()
        safe_id = _safe_segment(event_id)
        safe_ext = _safe_segment(ext.lstrip("."))
        return (
            f"{self.day_prefix(store_id, day)}event_{safe_id}.{safe_ext}"
        )

    def snapshot(
        self,
        *,
        store_id: int,
        snapshot_id: str,
        when: date | datetime | None = None,
        ext: str = "jpg",
    ) -> str:
        day = when if when is not None else datetime.now(UTC).date()
        safe_id = _safe_segment(snapshot_id)
        safe_ext = _safe_segment(ext.lstrip("."))
        return (
            f"{self.day_prefix(store_id, day)}snap_{safe_id}.{safe_ext}"
        )

    # ------------------------------------------------------------------
    # IAM policy template — documented so ops can stamp it per-tenant
    # ------------------------------------------------------------------

    def iam_policy(self, *, bucket: str) -> dict:
        """AWS/MinIO-compatible policy scoped to this tenant's prefix.

        The tenant's API key (or MinIO access key) gets this document
        attached at provisioning time so the key cannot GET/PUT into
        another tenant's prefix even if the application layer is
        bypassed.
        """
        arn_prefix = f"arn:aws:s3:::{bucket}/{self.tenant_prefix}*"
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": f"tenant_{self.tenant_id.replace('-', '_')}_rw",
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket",
                    ],
                    "Resource": [
                        f"arn:aws:s3:::{bucket}",
                        arn_prefix,
                    ],
                    "Condition": {
                        "StringLike": {
                            "s3:prefix": [f"{self.tenant_prefix}*"],
                        }
                    },
                },
            ],
        }


def key_belongs_to_tenant(
    key: str, *, tenant_id: UUID | str
) -> bool:
    """Pre-flight check for any write path that handles
    customer-provided object keys (exports, API uploads). Returns
    False for keys outside the tenant's prefix — handler should 403."""
    tid = _canonicalize(tenant_id)
    return key.startswith(f"tenant_{tid}/")

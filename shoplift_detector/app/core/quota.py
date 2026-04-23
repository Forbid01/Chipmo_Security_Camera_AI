"""Per-tenant resource quota enforcement (T1-07, DOC-05 §4).

Every plan ships a JSONB `resource_quota` on the tenant row. When a
caller tries to create a resource (camera, store, etc.) that would
exceed the plan limit, we raise 403 with a structured body that the
customer portal turns into an "Upgrade plan" CTA.

The quota dict is the source of truth at runtime; the defaults below
are only used when a tenant row is missing a key (pre-migration or
legacy tenant created before the dimension existed).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

# Plan-tier defaults per 03_Pricing §2 and DOC-05 §4.1. `None` means
# no cap. A missing key on a tenant.resource_quota JSONB falls back
# to these values — never hardcoded "unlimited".
PLAN_QUOTA_DEFAULTS: dict[str, dict[str, int | None]] = {
    "trial": {
        "max_cameras": 5,
        "max_stores": 1,
        "max_gpu_seconds_per_day": 21_600,
        "max_storage_gb": 10,
        "max_api_calls_per_minute": 30,
    },
    "starter": {
        "max_cameras": 5,
        "max_stores": 1,
        "max_gpu_seconds_per_day": 21_600,
        "max_storage_gb": 10,
        "max_api_calls_per_minute": 30,
    },
    "pro": {
        "max_cameras": 50,
        "max_stores": 10,
        "max_gpu_seconds_per_day": 86_400,
        "max_storage_gb": 100,
        "max_api_calls_per_minute": 60,
    },
    "enterprise": {
        "max_cameras": None,
        "max_stores": None,
        "max_gpu_seconds_per_day": None,
        "max_storage_gb": None,
        "max_api_calls_per_minute": 600,
    },
}


class QuotaExceededError(HTTPException):
    """403 with a machine-readable body so the customer portal can
    render an upgrade CTA next to the banner."""

    def __init__(self, *, dimension: str, limit: int, plan: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "quota_exceeded",
                "dimension": dimension,
                "limit": limit,
                "current_plan": plan,
                "message_mn": (
                    f"Одоогийн plan ({plan})-ийн {dimension} хязгаарт хүрсэн. "
                    f"Plan-аа өргөтгөнө үү."
                ),
                "upgrade_url": "/customer-portal/billing/plan",
            },
        )


def _resolve_limit(tenant: dict[str, Any], dimension: str) -> int | None:
    """Fish the limit out of tenant.resource_quota with a plan-tier
    fallback. Returns None for unlimited (Enterprise)."""
    quota = tenant.get("resource_quota") or {}
    if dimension in quota:
        value = quota[dimension]
    else:
        plan = tenant.get("plan") or "trial"
        value = PLAN_QUOTA_DEFAULTS.get(plan, PLAN_QUOTA_DEFAULTS["trial"]).get(
            dimension
        )
    # JSONB sometimes round-trips numerics as strings ("50"); coerce.
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return value  # type: ignore[return-value]


def ensure_can_add(
    tenant: dict[str, Any],
    *,
    dimension: str,
    current_count: int,
) -> None:
    """Raise `QuotaExceededError` if adding one more would breach the
    tenant's limit for `dimension`. Safe no-op when the limit is None
    (Enterprise plan)."""
    limit = _resolve_limit(tenant, dimension)
    if limit is None:
        return
    if current_count >= limit:
        raise QuotaExceededError(
            dimension=dimension,
            limit=limit,
            plan=tenant.get("plan") or "trial",
        )


def ensure_camera_quota(tenant: dict[str, Any], current_count: int) -> None:
    """Shortcut — call before INSERT on cameras."""
    ensure_can_add(tenant, dimension="max_cameras", current_count=current_count)


def ensure_store_quota(tenant: dict[str, Any], current_count: int) -> None:
    """Shortcut — call before INSERT on stores."""
    ensure_can_add(tenant, dimension="max_stores", current_count=current_count)

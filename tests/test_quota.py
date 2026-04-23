"""Tests for T1-07 — plan-tier resource quota enforcement."""

import pytest
from fastapi import HTTPException

from shoplift_detector.app.core.quota import (
    PLAN_QUOTA_DEFAULTS,
    QuotaExceededError,
    ensure_camera_quota,
    ensure_can_add,
    ensure_store_quota,
)


def _tenant(plan: str, **quota) -> dict:
    return {
        "tenant_id": "t-1",
        "plan": plan,
        "resource_quota": quota,
    }


# ---------------------------------------------------------------------------
# Plan defaults
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plan,dimension,expected", [
    ("starter", "max_cameras", 5),
    ("starter", "max_stores", 1),
    ("pro", "max_cameras", 50),
    ("pro", "max_stores", 10),
    ("enterprise", "max_cameras", None),  # unlimited
    ("enterprise", "max_stores", None),
    ("trial", "max_cameras", 5),
])
def test_plan_defaults_match_pricing_doc(plan, dimension, expected):
    assert PLAN_QUOTA_DEFAULTS[plan][dimension] == expected


# ---------------------------------------------------------------------------
# Enforcement — allowed paths
# ---------------------------------------------------------------------------

def test_starter_can_add_fifth_camera_after_four():
    tenant = _tenant("starter", max_cameras=5)
    ensure_camera_quota(tenant, current_count=4)  # no raise


def test_enterprise_is_unlimited_even_at_huge_counts():
    tenant = _tenant("enterprise")
    ensure_camera_quota(tenant, current_count=10_000)
    ensure_store_quota(tenant, current_count=500)


def test_explicit_none_quota_means_unlimited():
    tenant = _tenant("pro", max_cameras=None)
    ensure_camera_quota(tenant, current_count=999)


def test_missing_resource_quota_falls_back_to_plan_defaults():
    tenant = {"tenant_id": "t-1", "plan": "pro", "resource_quota": None}
    ensure_camera_quota(tenant, current_count=49)  # pro default = 50


def test_unknown_plan_falls_back_to_trial_defaults():
    tenant = {"tenant_id": "t-1", "plan": "legacy", "resource_quota": {}}
    # trial default max_cameras = 5; 4 < 5 so OK
    ensure_camera_quota(tenant, current_count=4)
    # 5 >= 5 → should raise
    with pytest.raises(QuotaExceededError):
        ensure_camera_quota(tenant, current_count=5)


# ---------------------------------------------------------------------------
# Enforcement — denied paths
# ---------------------------------------------------------------------------

def test_starter_exceeded_raises_403_with_upgrade_cta():
    tenant = _tenant("starter", max_cameras=5)
    with pytest.raises(QuotaExceededError) as ctx:
        ensure_camera_quota(tenant, current_count=5)
    err: HTTPException = ctx.value
    assert err.status_code == 403
    body = err.detail
    assert body["error"] == "quota_exceeded"
    assert body["dimension"] == "max_cameras"
    assert body["limit"] == 5
    assert body["current_plan"] == "starter"
    assert "upgrade_url" in body
    # User-facing Mongolian message.
    assert "message_mn" in body


def test_pro_exceeded_at_store_limit():
    tenant = _tenant("pro", max_stores=10)
    with pytest.raises(QuotaExceededError):
        ensure_store_quota(tenant, current_count=10)


def test_store_quota_mentions_max_stores_dimension():
    tenant = _tenant("starter", max_stores=1)
    with pytest.raises(QuotaExceededError) as ctx:
        ensure_store_quota(tenant, current_count=1)
    assert ctx.value.detail["dimension"] == "max_stores"


# ---------------------------------------------------------------------------
# JSONB coercion
# ---------------------------------------------------------------------------

def test_string_encoded_number_is_coerced():
    # Some JSONB drivers hand back numeric quotas as strings.
    tenant = _tenant("pro", max_cameras="50")
    ensure_camera_quota(tenant, current_count=49)
    with pytest.raises(QuotaExceededError):
        ensure_camera_quota(tenant, current_count=50)


# ---------------------------------------------------------------------------
# ensure_can_add generic
# ---------------------------------------------------------------------------

def test_ensure_can_add_rejects_equal_to_limit():
    tenant = _tenant("pro", max_api_calls_per_minute=60)
    with pytest.raises(QuotaExceededError):
        ensure_can_add(tenant, dimension="max_api_calls_per_minute", current_count=60)


def test_ensure_can_add_allows_below_limit():
    tenant = _tenant("pro", max_api_calls_per_minute=60)
    ensure_can_add(tenant, dimension="max_api_calls_per_minute", current_count=59)

"""Tests for T1-13 — per-tenant MinIO bucket layout + IAM policy."""

from datetime import date, datetime

import pytest

from shoplift_detector.app.core.tenant_storage import (
    TenantBucketLayout,
    key_belongs_to_tenant,
)

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# Prefix building
# ---------------------------------------------------------------------------

def test_tenant_prefix_matches_doc_format():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    assert layout.tenant_prefix == f"tenant_{TENANT_A}/"


def test_store_prefix_nests_under_tenant():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    assert layout.store_prefix(5) == f"tenant_{TENANT_A}/store_5/"


def test_day_prefix_uses_isoformat_date():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    d = date(2026, 4, 22)
    assert layout.day_prefix(1, d) == f"tenant_{TENANT_A}/store_1/2026-04-22/"


def test_day_prefix_accepts_datetime_and_drops_time():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    dt = datetime(2026, 4, 22, 15, 30)
    assert layout.day_prefix(1, dt) == f"tenant_{TENANT_A}/store_1/2026-04-22/"


# ---------------------------------------------------------------------------
# File keys
# ---------------------------------------------------------------------------

def test_event_clip_has_canonical_shape():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    key = layout.event_clip(
        store_id=1,
        event_id="abc123",
        when=date(2026, 4, 22),
    )
    assert key == f"tenant_{TENANT_A}/store_1/2026-04-22/event_abc123.mp4"


def test_event_clip_defaults_to_mp4():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    key = layout.event_clip(
        store_id=1, event_id="x", when=date(2026, 4, 22)
    )
    assert key.endswith(".mp4")


def test_snapshot_has_distinct_prefix_from_clip():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    clip = layout.event_clip(store_id=1, event_id="x", when=date(2026, 4, 22))
    snap = layout.snapshot(store_id=1, snapshot_id="x", when=date(2026, 4, 22))
    assert clip != snap
    assert "event_" in clip
    assert "snap_" in snap


def test_event_clip_strips_leading_dot_from_extension():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    key = layout.event_clip(
        store_id=1, event_id="x", when=date(2026, 4, 22), ext=".mkv"
    )
    assert key.endswith(".mkv")


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------

def test_event_id_traversal_segments_sanitized():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    key = layout.event_clip(
        store_id=1,
        event_id="../../etc/passwd",
        when=date(2026, 4, 22),
    )
    assert "../" not in key
    assert key.startswith(layout.tenant_prefix)


def test_event_id_cannot_be_dot_or_dotdot():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    with pytest.raises(ValueError):
        layout.event_clip(store_id=1, event_id="..", when=date(2026, 4, 22))


def test_extension_is_sanitized_too():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    key = layout.event_clip(
        store_id=1,
        event_id="x",
        when=date(2026, 4, 22),
        ext="mp4/../shenanigans",
    )
    assert "../" not in key


# ---------------------------------------------------------------------------
# Tenant isolation check
# ---------------------------------------------------------------------------

def test_key_belongs_to_tenant_happy_path():
    assert key_belongs_to_tenant(
        f"tenant_{TENANT_A}/store_1/file.mp4",
        tenant_id=TENANT_A,
    ) is True


def test_key_belongs_to_different_tenant_rejected():
    assert key_belongs_to_tenant(
        f"tenant_{TENANT_A}/store_1/file.mp4",
        tenant_id=TENANT_B,
    ) is False


def test_key_without_tenant_prefix_rejected():
    assert key_belongs_to_tenant(
        "orphan/store_1/file.mp4",
        tenant_id=TENANT_A,
    ) is False


# ---------------------------------------------------------------------------
# IAM policy
# ---------------------------------------------------------------------------

def test_iam_policy_scoped_to_tenant_prefix():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    policy = layout.iam_policy(bucket="sentry-clips")
    stmt = policy["Statement"][0]
    # Sid identifies the tenant so ops can diff policies easily.
    assert TENANT_A.replace("-", "_") in stmt["Sid"]
    # Resource list restricts to the tenant's prefix only.
    assert any(
        f"tenant_{TENANT_A}/" in arn for arn in stmt["Resource"]
    )
    # Condition also restricts ListBucket to the prefix.
    condition = stmt["Condition"]["StringLike"]["s3:prefix"]
    assert condition == [f"tenant_{TENANT_A}/*"]


def test_iam_policy_allows_rw_not_wildcard():
    layout = TenantBucketLayout(tenant_id=TENANT_A)
    policy = layout.iam_policy(bucket="sentry-clips")
    actions = policy["Statement"][0]["Action"]
    # Explicit action list only — no `s3:*` wildcards.
    assert "s3:*" not in actions
    assert "s3:GetObject" in actions
    assert "s3:PutObject" in actions
    assert "s3:DeleteObject" in actions


# ---------------------------------------------------------------------------
# Construction validation (shared with TenantKeys)
# ---------------------------------------------------------------------------

def test_layout_rejects_empty_tenant_id():
    with pytest.raises(ValueError):
        TenantBucketLayout(tenant_id="")


def test_layout_rejects_non_uuid():
    with pytest.raises(ValueError):
        TenantBucketLayout(tenant_id="store-1")

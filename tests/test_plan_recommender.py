"""Tests for T2-06 — plan picker logic."""

import pytest

from shoplift_detector.app.services.plan_recommender import (
    ANNUAL_DISCOUNT_PCT,
    PLAN_FEATURES,
    build_picker,
    recommend_plan,
)


# ---------------------------------------------------------------------------
# recommend_plan — tier boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cams,expected", [
    (1, "starter"),
    (5, "starter"),
    (6, "pro"),
    (20, "pro"),
    (50, "pro"),
    (51, "enterprise"),
    (200, "enterprise"),
])
def test_recommend_plan_by_camera_count(cams, expected):
    assert recommend_plan(camera_count=cams, store_count=1) == expected


@pytest.mark.parametrize("stores,expected", [
    (1, "starter"),
    (2, "pro"),
    (10, "pro"),
    (11, "enterprise"),
])
def test_store_count_upshifts_recommendation(stores, expected):
    # With 3 cameras across many stores, the recommendation should
    # follow the store-count bucket, not the camera bucket.
    assert recommend_plan(camera_count=3, store_count=stores) == expected


def test_recommend_plan_rejects_invalid_counts():
    with pytest.raises(ValueError):
        recommend_plan(camera_count=0, store_count=1)
    with pytest.raises(ValueError):
        recommend_plan(camera_count=1, store_count=0)


# ---------------------------------------------------------------------------
# Feature catalog
# ---------------------------------------------------------------------------

def test_feature_catalog_has_all_three_plans():
    assert set(PLAN_FEATURES.keys()) == {"starter", "pro", "enterprise"}


def test_enterprise_feature_list_mentions_dedicated_gpu_and_sso():
    features = " ".join(PLAN_FEATURES["enterprise"])
    assert "GPU" in features
    assert "SSO" in features or "SAML" in features


# ---------------------------------------------------------------------------
# Annual discount + picker output
# ---------------------------------------------------------------------------

def test_annual_discount_is_ten_percent():
    assert ANNUAL_DISCOUNT_PCT == pytest.approx(0.10)


def test_picker_marks_exactly_one_recommended_card():
    result = build_picker(camera_count=12, store_count=1)
    recommended = [c for c in result.cards if c.recommended]
    assert len(recommended) == 1
    assert recommended[0].plan == "pro"


def test_picker_annual_prepay_discounts_monthly():
    baseline = build_picker(
        camera_count=12, store_count=1, annual_prepay=False
    )
    discounted = build_picker(
        camera_count=12, store_count=1, annual_prepay=True
    )
    pro_base = next(c for c in baseline.cards if c.plan == "pro")
    pro_disc = next(c for c in discounted.cards if c.plan == "pro")
    # The `annual_monthly` is the discounted number; monthly_total
    # stays at list price so the UI can cross-out the old price.
    assert pro_disc.annual_monthly < pro_base.monthly_total
    assert pro_disc.monthly_total == pro_base.monthly_total


def test_picker_exposes_feature_bullets_for_each_card():
    result = build_picker(camera_count=5, store_count=1)
    for card in result.cards:
        assert card.features == PLAN_FEATURES[card.plan]


def test_picker_clamps_camera_count_into_each_tier():
    """With 50 cameras, the Starter card price is representative of
    Starter's cap (5), not 50 — otherwise comparing cards is unfair."""
    result = build_picker(camera_count=50, store_count=1)
    starter = next(c for c in result.cards if c.plan == "starter")
    pro = next(c for c in result.cards if c.plan == "pro")
    # Starter must be cheaper than Pro at the same user-entered count
    # thanks to the clamp.
    assert starter.monthly_total < pro.monthly_total


def test_picker_rejects_non_positive_counts():
    with pytest.raises(ValueError):
        build_picker(camera_count=0, store_count=1)
    with pytest.raises(ValueError):
        build_picker(camera_count=1, store_count=0)

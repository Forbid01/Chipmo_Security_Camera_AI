"""Tests for pricing service."""

import pytest

from shoplift_detector.app.services.pricing_service import (
    PLATFORM_FEE,
    calculate_monthly_bill,
    get_camera_rate,
)


class TestGetCameraRate:
    """Test per-camera rate based on volume tiers."""

    @pytest.mark.parametrize(
        "count, expected_rate",
        [
            (1, 20_000),
            (3, 20_000),
            (5, 20_000),   # upper edge of tier 1
            (6, 17_000),   # lower edge of tier 2
            (10, 17_000),
            (20, 17_000),  # upper edge of tier 2
            (21, 14_000),  # lower edge of tier 3
            (35, 14_000),
            (50, 14_000),  # upper edge of tier 3
            (51, 11_000),  # lower edge of tier 4
            (100, 11_000),
            (500, 11_000),
        ],
    )
    def test_tier_rates(self, count, expected_rate):
        assert get_camera_rate(count) == expected_rate

    def test_zero_cameras_raises(self):
        with pytest.raises(ValueError):
            get_camera_rate(0)

    def test_negative_cameras_raises(self):
        with pytest.raises(ValueError):
            get_camera_rate(-1)


class TestCalculateMonthlyBill:
    """Test full bill calculation."""

    def test_single_org_5_cameras(self):
        result = calculate_monthly_bill(camera_count=5, org_count=1)
        assert result["platform_fee_per_org"] == 29_000
        assert result["platform_total"] == 29_000
        assert result["camera_rate"] == 20_000
        assert result["camera_total"] == 5 * 20_000
        assert result["grand_total"] == 29_000 + 100_000

    def test_single_org_6_cameras(self):
        result = calculate_monthly_bill(camera_count=6, org_count=1)
        assert result["camera_rate"] == 17_000
        assert result["camera_total"] == 6 * 17_000
        assert result["grand_total"] == 29_000 + 102_000

    def test_single_org_21_cameras(self):
        result = calculate_monthly_bill(camera_count=21, org_count=1)
        assert result["camera_rate"] == 14_000
        assert result["grand_total"] == 29_000 + 21 * 14_000

    def test_single_org_51_cameras(self):
        result = calculate_monthly_bill(camera_count=51, org_count=1)
        assert result["camera_rate"] == 11_000
        assert result["grand_total"] == 29_000 + 51 * 11_000

    def test_multiple_orgs(self):
        result = calculate_monthly_bill(camera_count=10, org_count=3)
        assert result["platform_total"] == 3 * 29_000
        assert result["grand_total"] == 3 * 29_000 + 10 * 17_000

    def test_zero_cameras(self):
        result = calculate_monthly_bill(camera_count=0, org_count=1)
        assert result["camera_rate"] == 0
        assert result["camera_total"] == 0
        assert result["grand_total"] == 29_000

    def test_invalid_org_count(self):
        with pytest.raises(ValueError):
            calculate_monthly_bill(camera_count=5, org_count=0)

    def test_negative_cameras(self):
        with pytest.raises(ValueError):
            calculate_monthly_bill(camera_count=-1, org_count=1)

    def test_formula(self):
        """Verify: total = (org_count × 29000) + (camera_count × per_camera_rate)"""
        for cameras, orgs in [(1, 1), (5, 2), (20, 1), (50, 3), (51, 1), (100, 5)]:
            result = calculate_monthly_bill(cameras, orgs)
            expected = orgs * PLATFORM_FEE + cameras * get_camera_rate(cameras)
            assert result["grand_total"] == expected

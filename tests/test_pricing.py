"""Tests for pricing service — SaaS + setup + visit fees."""

import pytest

from shoplift_detector.app.services.pricing_service import (
    PLATFORM_FEE,
    get_camera_rate,
    get_setup_rate,
    get_visit_fee,
    calculate_quote,
)


class TestGetCameraRate:
    """Monthly per-camera rate volume tiers."""

    @pytest.mark.parametrize(
        "count, expected",
        [
            (1, 20_000), (5, 20_000),   # tier 1 edges
            (6, 17_000), (20, 17_000),  # tier 2 edges
            (21, 14_000), (50, 14_000), # tier 3 edges
            (51, 11_000), (100, 11_000),# tier 4
        ],
    )
    def test_tier_rates(self, count, expected):
        assert get_camera_rate(count) == expected

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            get_camera_rate(0)


class TestGetSetupRate:
    """One-time setup fee per camera — Chipmo tech vs self-setup."""

    @pytest.mark.parametrize(
        "count, self_setup, expected",
        [
            # Chipmo tech
            (1, False, 30_000), (5, False, 30_000),
            (6, False, 25_000), (20, False, 25_000),
            (21, False, 20_000), (50, False, 20_000),
            # Self-setup
            (1, True, 15_000), (5, True, 15_000),
            (6, True, 12_000), (20, True, 12_000),
            (21, True, 10_000), (50, True, 10_000),
        ],
    )
    def test_setup_rates(self, count, self_setup, expected):
        assert get_setup_rate(count, self_setup) == expected

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            get_setup_rate(0)


class TestGetVisitFee:
    """Visit/dispatch fee per store."""

    def test_ub_single_store(self):
        assert get_visit_fee(1, "ub") == 50_000

    def test_ub_multiple_stores(self):
        # 1st = 50k, 2nd = 30k, 3rd = 30k
        assert get_visit_fee(3, "ub") == 50_000 + 2 * 30_000

    def test_remote_single(self):
        assert get_visit_fee(1, "remote") == 20_000

    def test_remote_multiple(self):
        assert get_visit_fee(5, "remote") == 5 * 20_000

    def test_self_no_fee(self):
        assert get_visit_fee(1, "self") == 0
        assert get_visit_fee(10, "self") == 0

    def test_invalid_location(self):
        with pytest.raises(ValueError):
            get_visit_fee(1, "mars")

    def test_zero_stores_raises(self):
        with pytest.raises(ValueError):
            get_visit_fee(0, "ub")


class TestCalculateQuote:
    """Full quote calculation."""

    def test_basic_5cam_1store_ub_chipmo(self):
        q = calculate_quote(5, 1, "ub", False)
        # Monthly
        assert q["monthly"]["platform_total"] == 29_000
        assert q["monthly"]["camera_rate"] == 20_000
        assert q["monthly"]["camera_total"] == 100_000
        assert q["monthly"]["total"] == 129_000
        # One-time
        assert q["one_time"]["setup_rate"] == 30_000
        assert q["one_time"]["setup_fee"] == 150_000
        assert q["one_time"]["visit_fee"] == 50_000
        assert q["one_time"]["total"] == 200_000
        # Summary
        assert q["summary"]["first_month_total"] == 129_000 + 200_000
        assert q["summary"]["monthly_total"] == 129_000
        assert q["summary"]["annual_total"] == 129_000 * 12 + 200_000

    def test_6cam_self_setup_self_visit(self):
        q = calculate_quote(6, 1, "self", True)
        assert q["monthly"]["camera_rate"] == 17_000
        assert q["one_time"]["setup_rate"] == 12_000
        assert q["one_time"]["setup_fee"] == 6 * 12_000
        assert q["one_time"]["visit_fee"] == 0
        assert q["one_time"]["total"] == 72_000

    def test_21cam_remote_chipmo(self):
        q = calculate_quote(21, 2, "remote", False)
        assert q["monthly"]["camera_rate"] == 14_000
        assert q["monthly"]["platform_total"] == 2 * 29_000
        assert q["monthly"]["total"] == 2 * 29_000 + 21 * 14_000
        assert q["one_time"]["setup_rate"] == 20_000
        assert q["one_time"]["visit_fee"] == 2 * 20_000

    def test_51cam_tier(self):
        q = calculate_quote(51, 1, "ub", False)
        assert q["monthly"]["camera_rate"] == 11_000
        assert q["one_time"]["setup_rate"] == 20_000

    def test_multiple_stores_ub_visit(self):
        q = calculate_quote(10, 3, "ub", False)
        assert q["one_time"]["visit_fee"] == 50_000 + 2 * 30_000

    def test_formula_consistency(self):
        """Verify: monthly = (store_count × 29000) + (camera_count × rate)"""
        for cams, stores in [(1, 1), (5, 2), (20, 1), (51, 3)]:
            q = calculate_quote(cams, stores, "ub", False)
            expected_monthly = stores * PLATFORM_FEE + cams * get_camera_rate(cams)
            assert q["monthly"]["total"] == expected_monthly
            assert q["summary"]["annual_total"] == expected_monthly * 12 + q["one_time"]["total"]

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            calculate_quote(0, 1)
        with pytest.raises(ValueError):
            calculate_quote(1, 0)

"""Tests for the AutoLearner threshold and weight adjustment logic."""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOPLIFT_DIR = os.path.join(BASE_DIR, "shoplift_detector")
if SHOPLIFT_DIR not in sys.path:
    sys.path.insert(0, SHOPLIFT_DIR)

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")

from shoplift_detector.app.services.auto_learner import AutoLearner, DEFAULT_WEIGHTS


@pytest.fixture
def learner():
    """A fresh AutoLearner instance for each test."""
    return AutoLearner()


# ---------------------------------------------------------------------------
# Threshold calculation
# ---------------------------------------------------------------------------

class TestThresholdCalculation:
    """Tests for AutoLearner._calculate_optimal_threshold."""

    @pytest.mark.autolearner
    def test_both_tp_and_fp_normal(self, learner):
        """When TP scores are higher than FP, threshold sits between them."""
        tp = [90.0, 95.0, 100.0]
        fp = [50.0, 55.0, 60.0]
        threshold = learner._calculate_optimal_threshold(tp, fp)
        avg_tp = sum(tp) / len(tp)  # 95
        avg_fp = sum(fp) / len(fp)  # 55
        # Expected: 55 * 0.4 + 95 * 0.6 = 22 + 57 = 79.0
        assert 40.0 <= threshold <= 150.0
        assert threshold == pytest.approx(79.0, abs=0.5)

    @pytest.mark.autolearner
    def test_fp_higher_than_tp(self, learner):
        """When FP average exceeds TP average, threshold is raised."""
        tp = [40.0, 45.0]
        fp = [80.0, 90.0]
        threshold = learner._calculate_optimal_threshold(tp, fp)
        avg_fp = sum(fp) / len(fp)  # 85
        # max(avg_tp, avg_fp) * 1.1 = 85 * 1.1 = 93.5
        assert threshold == pytest.approx(93.5, abs=0.5)

    @pytest.mark.autolearner
    def test_only_true_positives(self, learner):
        """With only TP data, threshold is set below the minimum TP score."""
        tp = [70.0, 80.0, 90.0]
        threshold = learner._calculate_optimal_threshold(tp, [])
        # min_tp * 0.85 = 70 * 0.85 = 59.5
        assert threshold == pytest.approx(59.5, abs=0.5)

    @pytest.mark.autolearner
    def test_only_false_positives(self, learner):
        """With only FP data, threshold is raised above the maximum FP score."""
        fp = [60.0, 70.0, 80.0]
        threshold = learner._calculate_optimal_threshold([], fp)
        # max_fp * 1.3 = 80 * 1.3 = 104.0
        assert threshold == pytest.approx(104.0, abs=0.5)

    @pytest.mark.autolearner
    def test_empty_inputs_return_default(self, learner):
        """No TP or FP data returns the default 80.0."""
        assert learner._calculate_optimal_threshold([], []) == 80.0

    @pytest.mark.autolearner
    def test_threshold_clamped_lower_bound(self, learner):
        """Extremely low TP scores are clamped to >= 40.0."""
        tp = [10.0, 12.0]
        threshold = learner._calculate_optimal_threshold(tp, [])
        assert threshold >= 40.0

    @pytest.mark.autolearner
    def test_threshold_clamped_upper_bound(self, learner):
        """Extremely high FP scores are clamped to <= 150.0."""
        fp = [200.0, 300.0]
        threshold = learner._calculate_optimal_threshold([], fp)
        assert threshold <= 150.0

    @pytest.mark.autolearner
    def test_single_tp_single_fp(self, learner):
        """Works with a single data point on each side."""
        tp = [100.0]
        fp = [50.0]
        threshold = learner._calculate_optimal_threshold(tp, fp)
        # 50*0.4 + 100*0.6 = 20 + 60 = 80.0
        assert threshold == pytest.approx(80.0, abs=0.5)

    @pytest.mark.autolearner
    def test_identical_tp_and_fp_scores(self, learner):
        """When TP and FP scores are equal, threshold is raised by 10%."""
        scores = [75.0, 75.0]
        threshold = learner._calculate_optimal_threshold(scores, scores)
        # avg_tp == avg_fp, so the else branch: max(75,75)*1.1 = 82.5
        assert threshold == pytest.approx(82.5, abs=0.5)


# ---------------------------------------------------------------------------
# Weight adjustment logic
# ---------------------------------------------------------------------------

class TestWeightAdjustment:
    """Tests for AutoLearner._adjust_weights."""

    @pytest.mark.autolearner
    async def test_weights_default_when_no_data(self, learner):
        """With no feedback, weights remain at default values."""
        db = AsyncMock()
        result = await learner._adjust_weights(db, store_id=1, feedback_data=[])
        assert result == DEFAULT_WEIGHTS

    @pytest.mark.autolearner
    async def test_weight_increases_for_tp_dominant_behavior(self, learner):
        """A behavior seen mostly in TPs gets its weight increased."""
        # Create feedback where 'looking_around' appears in 8 TPs and 2 FPs
        feedback = []
        for _ in range(8):
            feedback.append({
                "feedback_type": "true_positive",
                "description": "Орчноо харах хийж байна",
            })
        for _ in range(2):
            feedback.append({
                "feedback_type": "false_positive",
                "description": "Орчноо харах хийж байна",
            })

        db = AsyncMock()
        weights = await learner._adjust_weights(db, store_id=1, feedback_data=feedback)

        # tp_ratio = 8/10 = 0.8, adjustment = 0.5 + 0.8 = 1.3
        expected = round(DEFAULT_WEIGHTS["looking_around"] * 1.3, 2)
        assert weights["looking_around"] == pytest.approx(expected, abs=0.01)

    @pytest.mark.autolearner
    async def test_weight_decreases_for_fp_dominant_behavior(self, learner):
        """A behavior seen mostly in FPs gets its weight decreased."""
        feedback = []
        for _ in range(2):
            feedback.append({
                "feedback_type": "true_positive",
                "description": "Хурдан хөдөлгөөн",
            })
        for _ in range(8):
            feedback.append({
                "feedback_type": "false_positive",
                "description": "Хурдан хөдөлгөөн",
            })

        db = AsyncMock()
        weights = await learner._adjust_weights(db, store_id=1, feedback_data=feedback)

        # tp_ratio = 2/10 = 0.2, adjustment = 0.5 + 0.2 = 0.7
        expected = round(DEFAULT_WEIGHTS["rapid_movement"] * 0.7, 2)
        assert weights["rapid_movement"] == pytest.approx(expected, abs=0.01)

    @pytest.mark.autolearner
    async def test_weight_unchanged_below_threshold(self, learner):
        """Behaviors with fewer than 5 total data points keep default weights."""
        feedback = []
        for _ in range(3):
            feedback.append({
                "feedback_type": "true_positive",
                "description": "Бөхийх",
            })
        for _ in range(1):
            feedback.append({
                "feedback_type": "false_positive",
                "description": "Бөхийх",
            })

        db = AsyncMock()
        weights = await learner._adjust_weights(db, store_id=1, feedback_data=feedback)

        # Only 4 data points < 5 threshold, so weight stays at default
        assert weights["crouch"] == DEFAULT_WEIGHTS["crouch"]

    @pytest.mark.autolearner
    async def test_multiple_behaviors_adjusted_independently(self, learner):
        """Different behaviors in the same feedback get independent adjustments."""
        feedback = []
        # 6 TPs with both looking_around and item_pickup
        for _ in range(6):
            feedback.append({
                "feedback_type": "true_positive",
                "description": "Орчноо харах, авах хийж байна",
            })
        # 4 FPs with only looking_around
        for _ in range(4):
            feedback.append({
                "feedback_type": "false_positive",
                "description": "Орчноо харах",
            })

        db = AsyncMock()
        weights = await learner._adjust_weights(db, store_id=1, feedback_data=feedback)

        # looking_around: 10 total (6 TP, 4 FP) -> ratio=0.6, adj=1.1
        # item_pickup: 6 total (6 TP, 0 FP) -> ratio=1.0, adj=1.5
        assert weights["looking_around"] < weights["item_pickup"]

    @pytest.mark.autolearner
    async def test_unrecognized_description_leaves_weights_default(self, learner):
        """Descriptions without known keywords do not affect any weights."""
        feedback = [
            {"feedback_type": "true_positive", "description": "Unknown behavior xyz"}
            for _ in range(10)
        ]

        db = AsyncMock()
        weights = await learner._adjust_weights(db, store_id=1, feedback_data=feedback)
        assert weights == DEFAULT_WEIGHTS


# ---------------------------------------------------------------------------
# Behavior extraction
# ---------------------------------------------------------------------------

class TestBehaviorExtraction:
    """Tests for AutoLearner._extract_behaviors."""

    @pytest.mark.autolearner
    def test_extracts_known_behaviors(self, learner):
        desc = "Орчноо харах, Биеэр далдлах, Бөхийх"
        result = learner._extract_behaviors(desc)
        assert "looking_around" in result
        assert "body_block" in result
        assert "crouch" in result

    @pytest.mark.autolearner
    def test_returns_empty_for_unknown_text(self, learner):
        result = learner._extract_behaviors("Nothing relevant here")
        assert result == []

    @pytest.mark.autolearner
    def test_partial_match_works(self, learner):
        """The keyword 'авах' should match substrings in the description."""
        result = learner._extract_behaviors("Бараа авах оролдлого")
        assert "item_pickup" in result


# ---------------------------------------------------------------------------
# Store config
# ---------------------------------------------------------------------------

class TestStoreConfig:
    """Tests for AutoLearner.get_store_config."""

    @pytest.mark.autolearner
    def test_default_config_for_unknown_store(self, learner):
        """An unknown store returns the default threshold and weights."""
        config = learner.get_store_config(store_id=99999)
        assert config["threshold"] == 80.0
        assert config["weights"] == DEFAULT_WEIGHTS

    @pytest.mark.autolearner
    def test_cached_config_returned_after_learning(self, learner):
        """After manually inserting a config, get_store_config returns it."""
        custom = {"threshold": 65.0, "weights": {"looking_around": 2.0}}
        learner._store_configs[42] = custom
        assert learner.get_store_config(42) == custom

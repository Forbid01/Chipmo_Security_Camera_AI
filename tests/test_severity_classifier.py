"""Tests for the 4-level severity classifier (T5-01).

The classifier replaces the single `alert_threshold` check in
`ai_service.ShopliftDetector` with a per-store GREEN/YELLOW/ORANGE/RED
tiering. These tests pin the contract — defaults, boundary behavior,
validation — so a future threshold tweak can't silently shift how
alerts get classified in production.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-severity")

from app.core.severity import (  # noqa: E402
    DEFAULT_SEVERITY_THRESHOLDS,
    NOTIFY_SEVERITIES,
    SEVERITY_LEVELS,
    SeverityThresholds,
    classify_severity,
)
from app.schemas.store_settings import (  # noqa: E402
    SeverityThresholdsSchema,
    StoreSettings,
    resolve_settings,
)


# ---------------------------------------------------------------------------
# Defaults — T5 spec
# ---------------------------------------------------------------------------

def test_defaults_match_t5_spec():
    assert DEFAULT_SEVERITY_THRESHOLDS.yellow == 40.0
    assert DEFAULT_SEVERITY_THRESHOLDS.orange == 70.0
    assert DEFAULT_SEVERITY_THRESHOLDS.red == 85.0


def test_severity_levels_ordered_and_complete():
    assert SEVERITY_LEVELS == ("green", "yellow", "orange", "red")


def test_notify_severities_excludes_green():
    assert "green" not in NOTIFY_SEVERITIES
    assert NOTIFY_SEVERITIES == frozenset({"yellow", "orange", "red"})


# ---------------------------------------------------------------------------
# Classification — boundaries matter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    # Below yellow → green
    (-1.0, "green"),
    (0.0, "green"),
    (39.9, "green"),
    # At / above yellow → yellow (inclusive lower bound)
    (40.0, "yellow"),
    (40.1, "yellow"),
    (69.9, "yellow"),
    # At / above orange → orange
    (70.0, "orange"),
    (70.1, "orange"),
    (84.9, "orange"),
    # At / above red → red
    (85.0, "red"),
    (100.0, "red"),
    (999.9, "red"),
])
def test_default_classifier_boundaries(score, expected):
    assert classify_severity(score) == expected


def test_custom_thresholds_override_defaults():
    thresholds = SeverityThresholds(yellow=20.0, orange=50.0, red=90.0)
    assert thresholds.classify(19.9) == "green"
    assert thresholds.classify(20.0) == "yellow"
    assert thresholds.classify(49.9) == "yellow"
    assert thresholds.classify(50.0) == "orange"
    assert thresholds.classify(90.0) == "red"


# ---------------------------------------------------------------------------
# Validation — bad input fails loudly
# ---------------------------------------------------------------------------

def test_negative_threshold_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        SeverityThresholds(yellow=-1.0, orange=50.0, red=90.0)


def test_non_increasing_rejected():
    with pytest.raises(ValueError, match="strictly increasing"):
        SeverityThresholds(yellow=50.0, orange=50.0, red=90.0)


def test_descending_rejected():
    with pytest.raises(ValueError, match="strictly increasing"):
        SeverityThresholds(yellow=90.0, orange=50.0, red=10.0)


# ---------------------------------------------------------------------------
# StoreSettings integration — round-trip and validation
# ---------------------------------------------------------------------------

def test_store_settings_default_includes_severity_thresholds():
    s = StoreSettings()
    assert s.severity_thresholds.yellow == 40.0
    assert s.severity_thresholds.orange == 70.0
    assert s.severity_thresholds.red == 85.0


def test_store_settings_accepts_custom_severity_thresholds():
    s = StoreSettings(
        severity_thresholds=SeverityThresholdsSchema(
            yellow=25.0, orange=55.0, red=80.0
        )
    )
    assert s.severity_thresholds.yellow == 25.0
    assert s.severity_thresholds.red == 80.0


def test_store_settings_rejects_non_increasing_thresholds():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="strictly increasing"):
        StoreSettings(
            severity_thresholds=SeverityThresholdsSchema(
                yellow=60.0, orange=60.0, red=80.0
            )
        )


def test_resolve_settings_backfills_severity_defaults():
    """An existing row that predates T5-01 has no severity_thresholds
    key; resolve_settings must still produce a valid config."""
    stored = {"alert_threshold": 75.0}
    resolved = resolve_settings(stored)
    assert resolved.severity_thresholds.yellow == 40.0
    assert resolved.severity_thresholds.red == 85.0


def test_resolve_settings_round_trips_custom_thresholds():
    stored = {
        "severity_thresholds": {"yellow": 30.0, "orange": 60.0, "red": 90.0}
    }
    resolved = resolve_settings(stored)
    assert resolved.severity_thresholds.orange == 60.0
    assert resolved.severity_thresholds.classify(89.9) == "orange"
    assert resolved.severity_thresholds.classify(90.0) == "red"

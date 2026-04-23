"""Tests for T2-10 — onboarding funnel dashboard + alert config."""

import json
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "observability" / "posthog" / "onboarding-funnel.json"
ALERTS = REPO / "observability" / "posthog" / "onboarding-dropoff-alert.yml"

# Canonical funnel order — must match the runtime event names and
# the frontend/backend event catalogs (T2-09).
EXPECTED_FUNNEL = [
    "signup_started",
    "signup_completed",
    "email_verified",
    "plan_selected",
    "trial_activated",
    "installer_downloaded",
    "agent_connected",
    "camera_connected",
    "first_detection",
]


@pytest.fixture(scope="module")
def dashboard():
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alerts():
    return yaml.safe_load(ALERTS.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Dashboard contract
# ---------------------------------------------------------------------------

def test_dashboard_is_funnel_insight(dashboard):
    assert dashboard["insight"] == "FUNNELS"
    assert dashboard["filters"]["insight"] == "FUNNELS"


def test_dashboard_funnel_events_match_catalog(dashboard):
    events = [e["id"] for e in dashboard["filters"]["events"]]
    assert events == EXPECTED_FUNNEL


def test_dashboard_events_are_ordered(dashboard):
    orders = [e["order"] for e in dashboard["filters"]["events"]]
    assert orders == list(range(len(EXPECTED_FUNNEL)))


def test_dashboard_has_time_to_first_detection_tile(dashboard):
    tiles = dashboard.get("dashboard_tiles", [])
    names = [t.get("name", "") for t in tiles]
    assert any("time-to-first-detection" in n.lower() for n in names)


def test_dashboard_defaults_to_thirty_day_window(dashboard):
    assert dashboard["filters"]["date_from"] == "-30d"


# ---------------------------------------------------------------------------
# Alerts contract
# ---------------------------------------------------------------------------

def test_alerts_declares_slack_channel(alerts):
    channel = alerts["notification_channel"]
    assert channel["type"] == "slack"
    assert channel["channel"] == "#onboarding-funnel"
    # Webhook must be env-referenced, never hardcoded.
    assert "webhook_env" in channel


def test_alerts_cover_every_critical_conversion_step(alerts):
    names = {a["name"] for a in alerts["alerts"]}
    # Every step-to-step conversion in the funnel that we want a
    # Slack ping for.
    for needle in (
        "signup_started_to_signup_completed",
        "email_verified_to_plan_selected",
        "plan_selected_to_trial_activated",
        "trial_activated_to_first_detection",
    ):
        assert any(needle in n for n in names), f"missing alert for {needle}"


def test_trial_activated_to_first_detection_is_critical(alerts):
    # This is the 15-min SLO step — severity must reflect the
    # customer-visible commitment, not a warning.
    target = next(
        a for a in alerts["alerts"]
        if "trial_activated_to_first_detection" in a["name"]
    )
    assert target["severity"] == "critical"


def test_all_alerts_use_60_percent_threshold(alerts):
    conversion_alerts = [
        a for a in alerts["alerts"]
        if "conversion" in a["expression"]
    ]
    assert conversion_alerts, "expected at least one conversion alert"
    for a in conversion_alerts:
        # "< 0.60" in the expression body — 60% cut-off per T2-10 DoD.
        assert "< 0.60" in a["expression"], (
            f"alert {a['name']} missing 60% threshold"
        )


def test_slo_alert_threshold_matches_15_minutes(alerts):
    slo = next(
        a for a in alerts["alerts"]
        if "time_to_first_detection" in a["name"]
    )
    # 15 min = 900 seconds.
    assert "900" in slo["expression"]

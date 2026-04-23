"""Tests for T2-09 — server-side PostHog analytics client."""

import pytest

from shoplift_detector.app.services.analytics import (
    ANALYTICS_EVENTS,
    NullAnalyticsClient,
    build_analytics_client,
    capture,
    set_client,
)


def test_event_catalog_matches_frontend_names():
    # Must stay in sync with security-web/src/services/analytics.js
    # ANALYTICS_EVENTS (same snake_case string values).
    for name in (
        "signup_started",
        "signup_completed",
        "email_verified",
        "plan_selected",
        "trial_activated",
        "payment_started",
        "payment_completed",
        "installer_downloaded",
        "agent_connected",
        "camera_discovered",
        "camera_connected",
        "first_detection",
        "onboarding_completed",
    ):
        assert name in ANALYTICS_EVENTS.values()


def test_build_null_client_when_api_key_missing():
    client = build_analytics_client(api_key=None)
    assert isinstance(client, NullAnalyticsClient)


def test_build_real_client_when_api_key_present():
    client = build_analytics_client(api_key="phc_test")
    # Importing the class directly would loop back through the module,
    # so we duck-type the contract: has `capture` coroutine.
    assert hasattr(client, "capture")
    assert client.__class__.__name__ == "PostHogClient"


@pytest.mark.asyncio
async def test_null_client_records_every_call_without_network_io():
    client = NullAnalyticsClient()
    await client.capture(
        distinct_id="tenant-1", event="trial_activated",
        properties={"plan": "pro"},
    )
    await client.capture(
        distinct_id="tenant-1", event="first_detection",
        properties={},
    )
    assert len(client.captured) == 2
    assert client.captured[0]["event"] == "trial_activated"
    assert client.captured[1]["event"] == "first_detection"


@pytest.mark.asyncio
async def test_module_capture_routes_through_current_client():
    recorder = NullAnalyticsClient()
    set_client(recorder)
    try:
        await capture(
            distinct_id="tenant-1", event="agent_connected",
            properties={"camera_count": 3},
        )
        assert len(recorder.captured) == 1
        assert recorder.captured[0]["properties"]["camera_count"] == 3
    finally:
        # Restore the default null client so unrelated tests don't
        # inherit this fixture's recorder.
        set_client(NullAnalyticsClient())


@pytest.mark.asyncio
async def test_module_capture_defaults_properties_to_empty_dict():
    recorder = NullAnalyticsClient()
    set_client(recorder)
    try:
        await capture(distinct_id="t-1", event="signup_started")
        assert recorder.captured[0]["properties"] == {}
    finally:
        set_client(NullAnalyticsClient())

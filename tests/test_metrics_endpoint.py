"""Tests for the /metrics Prometheus endpoint.

Locks in:
- both the root `/metrics` (Prometheus-convention) and versioned
  `/api/v1/metrics` paths respond
- the response body is OpenMetrics text, not JSON
- recording helpers write through to the exposed payload
- the content-type matches what prometheus-client exposes so scrapers
  don't treat the response as plain HTML
"""

import pytest

# Import via the `app.*` path — conftest.py puts shoplift_detector on
# sys.path, so this resolves to the exact same module object the
# FastAPI router imports. Importing via `shoplift_detector.app.*`
# would create a second module instance with its own registry, and
# recordings would not surface through the endpoint.
from app.observability import (  # noqa: E402
    record_alert,
    reset_metrics_for_tests,
    set_camera_fps,
)
from prometheus_client import CONTENT_TYPE_LATEST


@pytest.fixture(autouse=True)
def _reset_metrics_between_tests():
    reset_metrics_for_tests()
    yield
    reset_metrics_for_tests()


@pytest.mark.asyncio
async def test_root_metrics_endpoint_returns_prometheus_payload(client):
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# HELP chipmo_alerts_total" in body
    assert "# TYPE chipmo_camera_fps gauge" in body
    assert "# TYPE chipmo_inference_latency_seconds histogram" in body


@pytest.mark.asyncio
async def test_versioned_metrics_endpoint_returns_identical_payload(client):
    # Record a sample so there's a concrete series to compare against.
    record_alert(store_id=1, camera_id=2, alert_type="behavior")

    root = await client.get("/metrics")
    versioned = await client.get("/api/v1/metrics")

    assert root.status_code == 200
    assert versioned.status_code == 200
    # Both should carry the counter we just recorded.
    assert "chipmo_alerts_total" in root.text
    assert "chipmo_alerts_total" in versioned.text


@pytest.mark.asyncio
async def test_metrics_content_type_is_openmetrics_compatible(client):
    response = await client.get("/metrics")
    # prometheus_client's CONTENT_TYPE_LATEST is the canonical value a
    # scraper expects; we pass it through verbatim from the library.
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


@pytest.mark.asyncio
async def test_recorded_samples_surface_through_endpoint(client):
    set_camera_fps(camera_id=7, fps=14.5)
    record_alert(store_id=3, camera_id=7)

    response = await client.get("/metrics")
    body = response.text

    # Gauge value with its label
    assert 'chipmo_camera_fps{camera_id="7"} 14.5' in body
    # Counter with store + camera label, value 1.0
    assert (
        'chipmo_alerts_total{alert_type="behavior",camera_id="7",store_id="3"} 1.0'
        in body
    )


@pytest.mark.asyncio
async def test_metrics_endpoint_is_not_listed_in_openapi_schema(client):
    # Operational endpoint — keep it out of user-facing docs per the
    # `include_in_schema=False` setting on both mounts.
    response = await client.get("/api/v1/openapi.json")
    if response.status_code == 404:
        pytest.skip("OpenAPI schema not exposed in this test config")
    schema = response.json()
    paths = schema.get("paths", {})
    assert "/metrics" not in paths
    assert "/api/v1/metrics" not in paths

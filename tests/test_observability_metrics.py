"""Tests for app.observability.metrics.

Locks in:
- every metric name required by docs/03-TECH-SPECS.md §3.1 is registered
  against CHIPMO_REGISTRY
- record helpers increment / set the correct series
- validation guards reject bad inputs before they hit Prometheus
- the timer context-manager records elapsed time even when the wrapped
  block raises
"""

import time

import pytest
from prometheus_client import generate_latest

from shoplift_detector.app.observability import metrics as m
from shoplift_detector.app.observability.metrics import (
    CHIPMO_REGISTRY,
    INFERENCE_STAGES,
    inference_stage_timer,
    observe_inference_latency,
    record_alert,
    record_feedback_verdict,
    registered_metric_names,
    reset_metrics_for_tests,
    set_camera_fps,
    set_camera_online,
    set_gpu_memory_bytes,
    set_gpu_utilization_percent,
)


@pytest.fixture(autouse=True)
def _reset_registry_between_tests():
    reset_metrics_for_tests()
    yield
    reset_metrics_for_tests()


def _sample_value(name: str, labels: dict[str, str]) -> float:
    """Look up a metric sample by its labels against CHIPMO_REGISTRY."""
    for metric in CHIPMO_REGISTRY.collect():
        for sample in metric.samples:
            if sample.name != name:
                continue
            if all(sample.labels.get(k) == v for k, v in labels.items()):
                return sample.value
    return 0.0


# ---------------------------------------------------------------------------
# Registration contract
# ---------------------------------------------------------------------------

def test_all_expected_metric_names_are_registered():
    # prometheus_client strips the `_total` suffix from Counter `.name`
    # but keeps it in the OpenMetrics text payload. Check the payload so
    # we assert against the exact strings that Grafana will scrape.
    payload = generate_latest(CHIPMO_REGISTRY).decode("utf-8")
    for name in registered_metric_names():
        assert name in payload, f"{name} not exposed on registry"


def test_inference_stage_tuple_matches_docs_spec():
    # docs/03-TECH-SPECS.md §3.1 lists yolo/reid/rag/vlm. We extended
    # with end_to_end to support the top-level pipeline bucket.
    assert set(INFERENCE_STAGES) == {"yolo", "reid", "rag", "vlm", "end_to_end"}


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

def test_record_alert_increments_counter_with_labels():
    record_alert(store_id=3, camera_id=7, alert_type="behavior")
    record_alert(store_id=3, camera_id=7, alert_type="behavior")

    value = _sample_value(
        "chipmo_alerts_total",
        {"store_id": "3", "camera_id": "7", "alert_type": "behavior"},
    )
    assert value == 2


def test_record_alert_coerces_none_to_unknown_label():
    record_alert(store_id=None, camera_id=None)

    value = _sample_value(
        "chipmo_alerts_total",
        {"store_id": "unknown", "camera_id": "unknown"},
    )
    assert value == 1


def test_record_feedback_verdict_routes_to_tp_fp_counters():
    record_feedback_verdict(store_id=1, verdict="true_positive")
    record_feedback_verdict(store_id=1, verdict="false_positive")
    record_feedback_verdict(store_id=1, verdict="false_positive")

    assert _sample_value("chipmo_true_positives_total", {"store_id": "1"}) == 1
    assert _sample_value("chipmo_false_positives_total", {"store_id": "1"}) == 2


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------

def test_observe_inference_latency_rejects_negative_value():
    with pytest.raises(ValueError, match="non-negative"):
        observe_inference_latency(camera_id=1, stage="yolo", seconds=-0.5)


def test_observe_inference_latency_rejects_unknown_stage():
    with pytest.raises(ValueError, match="Unknown inference stage"):
        observe_inference_latency(camera_id=1, stage="banana", seconds=0.05)


def test_observe_inference_latency_records_sum_and_count():
    observe_inference_latency(camera_id=5, stage="yolo", seconds=0.02)
    observe_inference_latency(camera_id=5, stage="yolo", seconds=0.08)

    count = _sample_value(
        "chipmo_inference_latency_seconds_count",
        {"camera_id": "5", "stage": "yolo"},
    )
    total = _sample_value(
        "chipmo_inference_latency_seconds_sum",
        {"camera_id": "5", "stage": "yolo"},
    )
    assert count == 2
    assert total == pytest.approx(0.10, abs=1e-6)


def test_inference_stage_timer_records_even_on_exception():
    with pytest.raises(RuntimeError), inference_stage_timer(camera_id=9, stage="vlm"):
        time.sleep(0.002)
        raise RuntimeError("simulated failure")

    count = _sample_value(
        "chipmo_inference_latency_seconds_count",
        {"camera_id": "9", "stage": "vlm"},
    )
    assert count == 1


def test_inference_stage_timer_rejects_unknown_stage_before_starting():
    with pytest.raises(ValueError), inference_stage_timer(camera_id=1, stage="warp"):
        pass  # pragma: no cover — should not enter


# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------

def test_set_gpu_memory_and_utilization_record_latest_sample():
    set_gpu_memory_bytes(gpu_id=0, bytes_used=4.2e9)
    set_gpu_memory_bytes(gpu_id=0, bytes_used=5.0e9)  # overwrites
    set_gpu_utilization_percent(gpu_id=0, percent=83.5)

    assert _sample_value(
        "chipmo_gpu_memory_used_bytes", {"gpu_id": "0"}
    ) == 5.0e9
    assert _sample_value(
        "chipmo_gpu_utilization_percent", {"gpu_id": "0"}
    ) == 83.5


def test_set_gpu_utilization_percent_bounds_checked():
    with pytest.raises(ValueError):
        set_gpu_utilization_percent(gpu_id=0, percent=101.0)
    with pytest.raises(ValueError):
        set_gpu_utilization_percent(gpu_id=0, percent=-1.0)


def test_set_camera_fps_rejects_negative():
    with pytest.raises(ValueError):
        set_camera_fps(camera_id=1, fps=-1.0)


def test_set_camera_online_coerces_bool_to_numeric_gauge():
    set_camera_online(camera_id=1, online=True)
    set_camera_online(camera_id=2, online=False)

    assert _sample_value("chipmo_camera_online", {"camera_id": "1"}) == 1
    assert _sample_value("chipmo_camera_online", {"camera_id": "2"}) == 0


# ---------------------------------------------------------------------------
# Text exposition — lets T02-09 be a thin wrapper around this registry
# ---------------------------------------------------------------------------

def test_generate_latest_contains_all_metric_families():
    record_alert(store_id=1, camera_id=1)
    set_camera_fps(camera_id=1, fps=14.5)

    payload = generate_latest(CHIPMO_REGISTRY).decode("utf-8")
    for name in registered_metric_names():
        assert name in payload, f"{name} missing from /metrics payload"


def test_reset_metrics_for_tests_clears_all_samples():
    record_alert(store_id=1, camera_id=1)
    assert _sample_value(
        "chipmo_alerts_total",
        {"store_id": "1", "camera_id": "1", "alert_type": "behavior"},
    ) == 1

    reset_metrics_for_tests()

    assert _sample_value(
        "chipmo_alerts_total",
        {"store_id": "1", "camera_id": "1", "alert_type": "behavior"},
    ) == 0


def test_module_reexports_helpers():
    # Ensures __init__ keeps the helper surface stable for downstream
    # modules that import from shoplift_detector.app.observability.
    from shoplift_detector.app import observability

    expected = {
        "record_alert",
        "record_feedback_verdict",
        "observe_inference_latency",
        "inference_stage_timer",
        "set_camera_fps",
        "set_camera_online",
        "set_gpu_memory_bytes",
        "set_gpu_utilization_percent",
        "reset_metrics_for_tests",
        "CHIPMO_REGISTRY",
        "INFERENCE_STAGES",
    }
    missing = expected - set(observability.__all__)
    assert not missing, f"observability.__init__ missing: {missing}"

    # And the names actually resolve
    for name in expected:
        assert hasattr(observability, name)


def test_module_uses_dedicated_registry_not_default():
    # Default registry sharing would cause duplicate-series errors when
    # pytest workers re-import. Pin this explicitly.
    from prometheus_client import REGISTRY as default_registry
    assert m.CHIPMO_REGISTRY is not default_registry

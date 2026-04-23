"""Prometheus metrics for the Chipmo backend.

Contract is locked by docs/03-TECH-SPECS.md §3.1. Metric names are
Prometheus-idiomatic (`_total` counters, `_seconds` histograms, base
units for gauges) so a generic Grafana dashboard matches out of the
box.

Design choices:
- A dedicated `CHIPMO_REGISTRY` so tests can reset without touching the
  global default registry, and so a future /metrics endpoint (T02-09)
  can expose exactly our metrics.
- Helper functions (`record_alert`, `observe_inference_latency`, …)
  encapsulate label construction. Callers pass plain ints / floats and
  the helper coerces to str. This keeps label cardinality accidents
  (e.g. a None sneaking into a label) out of the call sites.
- `inference_stage_timer` is a context manager so instrumentation can
  be one line at the call site:

      with inference_stage_timer(camera_id=42, stage="yolo"):
          pose_model.track(...)
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Literal

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Single dedicated registry. Do not use the module-level default
# registry — concurrent pytest workers, multiple FastAPI imports, or
# notebooks that re-import the module would raise "Duplicated timeseries"
# against the default registry.
CHIPMO_REGISTRY = CollectorRegistry()


INFERENCE_STAGES: tuple[str, ...] = (
    "yolo",
    "reid",
    "rag",
    "vlm",
    "end_to_end",
)

InferenceStage = Literal["yolo", "reid", "rag", "vlm", "end_to_end"]

FeedbackVerdict = Literal["true_positive", "false_positive"]


# --- Counters ---------------------------------------------------------------

alerts_total = Counter(
    "chipmo_alerts_total",
    "Total alerts emitted by the detection pipeline.",
    labelnames=("store_id", "camera_id", "alert_type"),
    registry=CHIPMO_REGISTRY,
)

true_positives_total = Counter(
    "chipmo_true_positives_total",
    "Alerts confirmed as true theft by user feedback.",
    labelnames=("store_id",),
    registry=CHIPMO_REGISTRY,
)

false_positives_total = Counter(
    "chipmo_false_positives_total",
    "Alerts labeled as false positive by user feedback.",
    labelnames=("store_id",),
    registry=CHIPMO_REGISTRY,
)


# --- Histograms -------------------------------------------------------------

# Buckets picked to separate sub-10 ms YOLO calls from multi-second VLM
# calls cleanly. Matches docs/03-TECH-SPECS.md §3.1.
_LATENCY_BUCKETS: tuple[float, ...] = (
    0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0,
)

inference_latency_seconds = Histogram(
    "chipmo_inference_latency_seconds",
    "End-to-end inference latency, observed per stage.",
    labelnames=("camera_id", "stage"),
    buckets=_LATENCY_BUCKETS,
    registry=CHIPMO_REGISTRY,
)


# --- Gauges -----------------------------------------------------------------

gpu_memory_used_bytes = Gauge(
    "chipmo_gpu_memory_used_bytes",
    "Resident GPU memory in bytes, per device index.",
    labelnames=("gpu_id",),
    registry=CHIPMO_REGISTRY,
)

gpu_utilization_percent = Gauge(
    "chipmo_gpu_utilization_percent",
    "GPU SM utilization percentage, per device index.",
    labelnames=("gpu_id",),
    registry=CHIPMO_REGISTRY,
)

camera_fps = Gauge(
    "chipmo_camera_fps",
    "Current inferred frames-per-second for each camera feed.",
    labelnames=("camera_id",),
    registry=CHIPMO_REGISTRY,
)

camera_online = Gauge(
    "chipmo_camera_online",
    "1 if the camera feed is currently streaming frames, else 0.",
    labelnames=("camera_id",),
    registry=CHIPMO_REGISTRY,
)


# ---------------------------------------------------------------------------
# Helpers — all call sites should go through these to avoid mismatched
# label ordering or types.
# ---------------------------------------------------------------------------

def record_alert(
    *,
    store_id: int | None,
    camera_id: int | None,
    alert_type: str = "behavior",
) -> None:
    alerts_total.labels(
        store_id=_label(store_id),
        camera_id=_label(camera_id),
        alert_type=alert_type,
    ).inc()


def record_feedback_verdict(
    *,
    store_id: int | None,
    verdict: FeedbackVerdict,
) -> None:
    counter = (
        true_positives_total
        if verdict == "true_positive"
        else false_positives_total
    )
    counter.labels(store_id=_label(store_id)).inc()


def observe_inference_latency(
    *,
    camera_id: int | None,
    stage: InferenceStage | str,
    seconds: float,
) -> None:
    if stage not in INFERENCE_STAGES:
        raise ValueError(
            f"Unknown inference stage '{stage}'. Allowed: {INFERENCE_STAGES}"
        )
    if seconds < 0:
        raise ValueError("Latency observation must be non-negative")
    inference_latency_seconds.labels(
        camera_id=_label(camera_id),
        stage=stage,
    ).observe(seconds)


@contextmanager
def inference_stage_timer(
    *,
    camera_id: int | None,
    stage: InferenceStage | str,
):
    """Context-manager form. Records elapsed seconds even on exception."""
    if stage not in INFERENCE_STAGES:
        raise ValueError(
            f"Unknown inference stage '{stage}'. Allowed: {INFERENCE_STAGES}"
        )
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        inference_latency_seconds.labels(
            camera_id=_label(camera_id),
            stage=stage,
        ).observe(elapsed)


def set_gpu_memory_bytes(*, gpu_id: int, bytes_used: float) -> None:
    gpu_memory_used_bytes.labels(gpu_id=_label(gpu_id)).set(float(bytes_used))


def set_gpu_utilization_percent(*, gpu_id: int, percent: float) -> None:
    if percent < 0 or percent > 100:
        raise ValueError("GPU utilization must be in [0, 100]")
    gpu_utilization_percent.labels(gpu_id=_label(gpu_id)).set(float(percent))


def set_camera_fps(*, camera_id: int | None, fps: float) -> None:
    if fps < 0:
        raise ValueError("fps must be non-negative")
    camera_fps.labels(camera_id=_label(camera_id)).set(float(fps))


def set_camera_online(*, camera_id: int | None, online: bool) -> None:
    camera_online.labels(camera_id=_label(camera_id)).set(1 if online else 0)


def reset_metrics_for_tests() -> None:
    """Clear all time-series on CHIPMO_REGISTRY.

    Only intended for pytest — do not call from production code. Uses the
    public `clear()` on each metric so we don't reach into private state.
    """
    for metric in (
        alerts_total,
        true_positives_total,
        false_positives_total,
        inference_latency_seconds,
        gpu_memory_used_bytes,
        gpu_utilization_percent,
        camera_fps,
        camera_online,
    ):
        # `_metrics` is the official mutable cache of per-label child
        # samples; `clear()` is not exposed on the public surface but
        # this is the idiomatic reset pattern the prometheus_client
        # tests themselves use.
        metric._metrics.clear()


def _label(value: int | str | None) -> str:
    """Coerce an int/None label to a bounded string.

    None becomes 'unknown' so we never emit an empty string label and
    never crash the recording call site. Callers that want strict
    validation should check before calling.
    """
    if value is None:
        return "unknown"
    return str(value)


# Expose the registered metric names up-front so downstream code / tests
# can iterate without poking into Prometheus internals.
def registered_metric_names() -> Iterable[str]:
    return (
        "chipmo_alerts_total",
        "chipmo_true_positives_total",
        "chipmo_false_positives_total",
        "chipmo_inference_latency_seconds",
        "chipmo_gpu_memory_used_bytes",
        "chipmo_gpu_utilization_percent",
        "chipmo_camera_fps",
        "chipmo_camera_online",
    )

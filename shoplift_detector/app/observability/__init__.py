"""Observability: Prometheus metrics definitions and helpers.

T02-08 delivers the metric surface. T02-09 wires it up to the
`/metrics` endpoint. Keep the two concerns separate so tests can
exercise recording without standing up FastAPI.
"""

from .metrics import (
    CHIPMO_REGISTRY,
    INFERENCE_STAGES,
    inference_stage_timer,
    observe_inference_latency,
    record_alert,
    record_feedback_verdict,
    reset_metrics_for_tests,
    set_camera_fps,
    set_camera_online,
    set_gpu_memory_bytes,
    set_gpu_utilization_percent,
)

__all__ = [
    "CHIPMO_REGISTRY",
    "INFERENCE_STAGES",
    "reset_metrics_for_tests",
    "set_camera_fps",
    "set_camera_online",
    "set_gpu_memory_bytes",
    "set_gpu_utilization_percent",
    "record_alert",
    "record_feedback_verdict",
    "observe_inference_latency",
    "inference_stage_timer",
]

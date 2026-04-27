"""Sentry edge agent — customer-side RTSP / ONVIF bridge to the cloud.

The agent runs on customer premises, discovers cameras over ONVIF,
captures frames via OpenCV, and forwards them to the Sentry cloud
backend under a per-tenant API key.

This module is the launch target of the Docker image built by
`agent/Dockerfile` (T4-01). Behavioral subsystems are filled in by
later tasks — T4-07 (register), T4-08 (heartbeat), T4-09 (ONVIF
discovery), T4-11 (test-connection).
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]

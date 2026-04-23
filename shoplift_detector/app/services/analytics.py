"""Server-side PostHog event emitter (T2-09).

Used for events the browser can't observe directly:

- agent_connected     (Docker agent's first heartbeat → T4-07)
- camera_discovered   (ONVIF probe returned a camera → T4-09)
- camera_connected    (RTSP test passed → T4-11)
- first_detection     (inference worker emitted its first alert)
- trial_activated     (server-side confirmation, not just the UI click)

Backend events ship through the PostHog `capture` REST endpoint. An
unset `POSTHOG_API_KEY` makes this module a no-op — handy for dev /
CI where we don't want to hit the wire.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


ANALYTICS_EVENTS: dict[str, str] = {
    "SIGNUP_STARTED": "signup_started",
    "SIGNUP_COMPLETED": "signup_completed",
    "EMAIL_VERIFIED": "email_verified",
    "PLAN_SELECTED": "plan_selected",
    "TRIAL_ACTIVATED": "trial_activated",
    "PAYMENT_STARTED": "payment_started",
    "PAYMENT_COMPLETED": "payment_completed",
    "INSTALLER_DOWNLOADED": "installer_downloaded",
    "AGENT_CONNECTED": "agent_connected",
    "CAMERA_DISCOVERED": "camera_discovered",
    "CAMERA_CONNECTED": "camera_connected",
    "FIRST_DETECTION": "first_detection",
    "ONBOARDING_COMPLETED": "onboarding_completed",
}


class AnalyticsClient(Protocol):
    async def capture(
        self, *, distinct_id: str, event: str, properties: dict[str, Any]
    ) -> None: ...


@dataclass
class NullAnalyticsClient:
    """No-op — used when PostHog isn't configured. Records calls for
    tests and dev-mode debugging."""

    captured: list[dict[str, Any]] = field(default_factory=list)

    async def capture(
        self, *, distinct_id: str, event: str, properties: dict[str, Any]
    ) -> None:
        self.captured.append(
            {
                "distinct_id": distinct_id,
                "event": event,
                "properties": dict(properties),
            }
        )


@dataclass
class PostHogClient:
    """httpx-based PostHog REST client. No batching — events are
    low-volume server-side (a few per tenant per day) so the
    per-event round-trip is cheaper than maintaining a background
    flusher thread.
    """

    api_key: str
    base_url: str = "https://app.posthog.com"
    timeout_seconds: float = 3.0

    async def capture(
        self,
        *,
        distinct_id: str,
        event: str,
        properties: dict[str, Any],
    ) -> None:
        payload = {
            "api_key": self.api_key,
            "event": event,
            "distinct_id": distinct_id,
            "properties": {**properties, "$lib": "sentry-server"},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as c:
                response = await c.post(f"{self.base_url}/capture/", json=payload)
                if response.status_code >= 400:
                    # Analytics must never break product flows — log
                    # at warning level and move on.
                    logger.warning(
                        "posthog_capture_rejected",
                        extra={
                            "status": response.status_code,
                            "body": response.text,
                        },
                    )
        except httpx.HTTPError as exc:
            logger.warning("posthog_capture_failed", extra={"error": str(exc)})


def build_analytics_client(api_key: str | None) -> AnalyticsClient:
    """Factory — returns the real client when configured, a null
    recorder otherwise. Keeps handlers from branching on settings."""
    if api_key:
        return PostHogClient(api_key=api_key)
    return NullAnalyticsClient()


# Module-level singleton convenience. The bootstrap may replace this
# with a live client during lifespan startup.
_client: AnalyticsClient = NullAnalyticsClient()


def set_client(client: AnalyticsClient) -> None:
    global _client  # noqa: PLW0603 — legitimate singleton hook
    _client = client


async def capture(
    *,
    distinct_id: str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Convenience — equivalent to `_client.capture(...)`."""
    await _client.capture(
        distinct_id=distinct_id,
        event=event,
        properties=properties or {},
    )


__all__ = [
    "ANALYTICS_EVENTS",
    "AnalyticsClient",
    "NullAnalyticsClient",
    "PostHogClient",
    "build_analytics_client",
    "capture",
    "set_client",
]

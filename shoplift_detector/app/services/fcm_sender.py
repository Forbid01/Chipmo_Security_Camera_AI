"""FCM push sender (T5-07).

Scaffolded on the same Protocol pattern as `email_sender` and
`sms_sender`: production wires a concrete sender, dev/tests wire the
recording fake. No hard dependency on `firebase-admin` — the HTTP
sender speaks directly to the FCM legacy send endpoint via httpx so
the base image stays small.

Upgrade path: swap `LegacyFcmSender` for a `FcmV1Sender` that uses
the Google service-account JWT flow once we add `google-auth` to the
dependency list. The protocol stays the same; callers don't change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OutgoingPush:
    token: str                # FCM device registration token
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)


class FcmUnavailableError(RuntimeError):
    """Provider-side outage — caller can retry later or fall through
    to another channel."""


class FcmSender(Protocol):
    async def send(self, message: OutgoingPush) -> str: ...


@dataclass
class RecordingFcmSender:
    sent: list[OutgoingPush] = field(default_factory=list)

    async def send(self, message: OutgoingPush) -> str:
        self.sent.append(message)
        return f"recorded-fcm-{len(self.sent)}"


@dataclass
class LegacyFcmSender:
    """FCM via the legacy HTTP `send` endpoint (server key auth).

    Requires `FCM_SERVER_KEY` env var. Google has deprecated this API
    in favour of the HTTP v1 protocol (service-account OAuth2), but
    it still works and is much smaller to ship without `google-auth`.
    Upgrade to `FcmV1Sender` when we need `send_multicast` batching.
    """

    server_key: str
    endpoint: str = "https://fcm.googleapis.com/fcm/send"
    timeout_seconds: float = 10.0

    async def send(self, message: OutgoingPush) -> str:
        payload: dict = {
            "to": message.token,
            "notification": {"title": message.title, "body": message.body},
            "priority": "high",
        }
        if message.data:
            payload["data"] = message.data

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"key={self.server_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            logger.warning("fcm_network_error", extra={"error": str(exc)})
            raise FcmUnavailableError(str(exc)) from exc

        if resp.status_code >= 500:
            raise FcmUnavailableError(
                f"FCM 5xx: {resp.status_code} {resp.text}"
            )
        if resp.status_code >= 400:
            logger.error(
                "fcm_rejected",
                extra={"status": resp.status_code, "body": resp.text},
            )
            raise RuntimeError(
                f"FCM refused the push: {resp.status_code} {resp.text}"
            )
        return str(resp.json().get("message_id", ""))


__all__ = [
    "FcmSender",
    "FcmUnavailableError",
    "LegacyFcmSender",
    "OutgoingPush",
    "RecordingFcmSender",
]

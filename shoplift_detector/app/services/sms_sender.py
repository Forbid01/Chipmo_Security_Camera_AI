"""SMS OTP delivery via Twilio (T2-03).

Twilio is the default provider (REST API via httpx). On provider
outage the caller pipes to email-only — `SmsUnavailableError` is
the signal for that fallback.
"""

from __future__ import annotations

import logging
from base64 import b64encode
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OutgoingSms:
    to: str       # E.164 form, e.g. +97688123456
    body: str     # plain text, <=160 chars keeps it single-segment


class SmsUnavailableError(RuntimeError):
    """Signal the caller to fall back to email-only OTP delivery."""


class SmsSender(Protocol):
    async def send(self, message: OutgoingSms) -> str: ...


@dataclass
class RecordingSmsSender:
    """Test / dev fallback. Stores every SMS it was asked to send."""

    sent: list[OutgoingSms] = field(default_factory=list)

    async def send(self, message: OutgoingSms) -> str:
        self.sent.append(message)
        return f"recorded-sms-{len(self.sent)}"


@dataclass
class TwilioSmsSender:
    account_sid: str
    auth_token: str
    from_number: str
    base_url: str = "https://api.twilio.com"
    timeout_seconds: float = 10.0

    async def send(self, message: OutgoingSms) -> str:
        url = (
            f"{self.base_url}/2010-04-01/Accounts/"
            f"{self.account_sid}/Messages.json"
        )
        credentials = b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()
        data = {
            "To": message.to,
            "From": self.from_number,
            "Body": message.body,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as c:
                response = await c.post(
                    url,
                    headers={"Authorization": f"Basic {credentials}"},
                    data=data,
                )
        except httpx.HTTPError as exc:
            logger.warning("twilio_network_error", extra={"error": str(exc)})
            raise SmsUnavailableError(str(exc)) from exc

        if response.status_code >= 500:
            # Provider-side outage — signal fallback to email.
            raise SmsUnavailableError(
                f"Twilio 5xx: {response.status_code} {response.text}"
            )
        if response.status_code >= 400:
            logger.error(
                "twilio_rejected",
                extra={
                    "status": response.status_code,
                    "body": response.text,
                },
            )
            raise RuntimeError(
                f"Twilio refused the SMS: {response.status_code} {response.text}"
            )
        return str(response.json().get("sid", ""))


def build_otp_sms(*, code: str) -> OutgoingSms:
    """Mongolian OTP SMS body. Kept short so it fits one segment."""
    return OutgoingSms(
        to="",  # caller fills in
        body=f"Sentry баталгаажуулах код: {code}",
    )

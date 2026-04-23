"""Transactional email delivery (T2-02).

Production uses Resend (https://resend.com). Dev/test uses an
in-memory fake so the signup flow doesn't depend on network I/O.

Pattern: abstract `EmailSender` protocol + concrete implementations
selected via settings. Handlers never import a concrete class
directly — they take the protocol and let the composition root wire
whichever backend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    from_addr: str = "Sentry <no-reply@sentry.mn>"
    reply_to: str | None = None


class EmailSender(Protocol):
    async def send(self, message: OutgoingEmail) -> str: ...


@dataclass
class RecordingEmailSender:
    """In-memory sender used by tests + local dev.

    Keeps every sent email in `sent` so tests can assert content.
    Returns a synthesized id so the production code path (which
    expects a provider id) still works.
    """

    sent: list[OutgoingEmail] = field(default_factory=list)

    async def send(self, message: OutgoingEmail) -> str:
        self.sent.append(message)
        return f"recorded-{len(self.sent)}"


@dataclass
class ResendEmailSender:
    """Thin wrapper around Resend's REST API.

    Kept separate from the protocol so tests don't need to monkey-
    patch httpx. Production bootstraps this with `RESEND_API_KEY`.
    """

    api_key: str
    base_url: str = "https://api.resend.com"
    timeout_seconds: float = 10.0

    async def send(self, message: OutgoingEmail) -> str:
        payload: dict = {
            "from": message.from_addr,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text_body,
        }
        if message.html_body:
            payload["html"] = message.html_body
        if message.reply_to:
            payload["reply_to"] = message.reply_to

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/emails",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                logger.error(
                    "resend_send_failed",
                    extra={
                        "status": response.status_code,
                        "body": response.text,
                    },
                )
                raise RuntimeError(
                    f"Resend refused the email: "
                    f"{response.status_code} {response.text}"
                )
            data = response.json()
            return str(data.get("id", ""))


def build_otp_email(*, to: str, code: str, store_name: str | None) -> OutgoingEmail:
    """Render the signup OTP email in Mongolian.

    Kept as a pure builder so tests can snapshot the template.
    """
    greeting = f"Сайн уу, {store_name}!" if store_name else "Сайн уу!"
    text_body = (
        f"{greeting}\n\n"
        f"Sentry-д бүртгэлээ баталгаажуулах код:\n\n"
        f"    {code}\n\n"
        f"Уг код 15 минутын дотор хүчинтэй. Хэрэв та бүртгүүлэхгүй байгаа "
        f"бол энэ имэйлийг үл тоомсорлоно уу."
    )
    html_body = (
        f"<p>{greeting}</p>"
        f"<p>Sentry-д бүртгэлээ баталгаажуулах код:</p>"
        f'<p style="font-size:32px;font-weight:600;letter-spacing:6px">'
        f"{code}</p>"
        f"<p>Уг код 15 минутын дотор хүчинтэй.</p>"
    )
    return OutgoingEmail(
        to=to,
        subject="Sentry баталгаажуулах код",
        text_body=text_body,
        html_body=html_body,
    )

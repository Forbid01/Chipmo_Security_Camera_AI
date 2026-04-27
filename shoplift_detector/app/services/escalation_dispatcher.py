"""Fan-out an approved alert across every configured channel (T5-06..09).

One call site in the AI pipeline (`ai_service._dispatch_alert`) feeds
this dispatcher the post-persist alert context. The dispatcher picks
the channels that apply to the severity, looks up recipients, sends
via the right provider, and logs each attempt to `alert_escalations`.

Severity gating:

* telegram → all non-green severities (yellow, orange, red)
* email    → all non-green severities
* fcm      → orange + red only (mobile-first, don't spam minor events)
* sms      → red only (per T5-08, and SMS costs money)

Per-recipient isolation: a failure on one chat / address does not
block the remaining recipients on that channel or the other channels.
Errors get logged to `alert_escalations.failed_at` + `error` so the
customer-portal viewer shows partial delivery cleanly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.db.repository.alert_escalations import AlertEscalationRepository
from app.db.repository.alerts import AlertRepository
from app.db.repository.push_tokens import PushTokenRepository
from app.db.repository.stores import StoreRepository
from app.db.repository.telegram_subscribers import (
    TelegramSubscriberRepository,
)
from app.db.session import AsyncSessionLocal
from app.schemas.store_settings import StoreSettings, resolve_settings
from app.services.alert_copy import (
    build_email_bodies,
    build_email_subject,
    build_fcm_payload,
    build_sms_body,
)
from app.services.email_sender import (
    EmailSender,
    OutgoingEmail,
    RecordingEmailSender,
    ResendEmailSender,
)
from app.services.fcm_sender import (
    FcmSender,
    LegacyFcmSender,
    OutgoingPush,
    RecordingFcmSender,
)
from app.services.sms_sender import (
    OutgoingSms,
    RecordingSmsSender,
    SmsSender,
    SmsUnavailableError,
    TwilioSmsSender,
)
from app.services.telegram_notifier import telegram_notifier

logger = logging.getLogger(__name__)


# T5-08 SMS rate limit: 1 SMS / 5 min / phone number / tenant.
# In-memory bucket keyed by (tenant_id, phone) → last-send monotonic
# time. A small cache suffices because SMS is RED-only and RED
# severity in a single store is already rare.
SMS_RATE_LIMIT_WINDOW_S = 300  # 5 min
_SMS_LAST_SENT: dict[tuple[str, str], float] = {}


@dataclass
class AlertContext:
    alert_id: int
    store_id: int | None
    camera_id: int | None
    severity: str  # "yellow" | "orange" | "red"
    reason: str
    image_path: str | None
    score: float | None
    tenant_id: str | None = None


def _sms_rate_limited(tenant_id: str, phone: str) -> bool:
    """Return True when the (tenant, phone) pair has sent an SMS
    within `SMS_RATE_LIMIT_WINDOW_S`. Updates the last-send stamp as
    a side-effect when the call is NOT rate-limited."""
    key = (tenant_id, phone)
    now = time.monotonic()
    last = _SMS_LAST_SENT.get(key)
    if last is not None and (now - last) < SMS_RATE_LIMIT_WINDOW_S:
        return True
    _SMS_LAST_SENT[key] = now
    return False


def _build_email_sender() -> EmailSender:
    """Resend in prod, in-memory recorder when RESEND_API_KEY unset."""
    api_key = (settings.RESEND_API_KEY or "").strip()
    if api_key:
        return ResendEmailSender(api_key=api_key)
    return RecordingEmailSender()


def _build_sms_sender() -> SmsSender | None:
    """Twilio if all three creds set, else None (channel disabled)."""
    sid = settings.TWILIO_ACCOUNT_SID
    token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_FROM_NUMBER
    if sid and token and from_number:
        return TwilioSmsSender(
            account_sid=sid,
            auth_token=token,
            from_number=from_number,
        )
    return RecordingSmsSender()


def _build_fcm_sender() -> FcmSender | None:
    """Legacy FCM server-key sender if FCM_SERVER_KEY set, else recorder."""
    key = (getattr(settings, "FCM_SERVER_KEY", "") or "").strip()
    if key:
        return LegacyFcmSender(server_key=key)
    return RecordingFcmSender()


async def dispatch_alert(
    context: AlertContext,
    *,
    email_sender: EmailSender | None = None,
    sms_sender: SmsSender | None = None,
    fcm_sender: FcmSender | None = None,
) -> None:
    """Fan-out the alert across every applicable channel.

    Never raises: a broken provider must not bubble up into the AI
    inference thread. Each per-recipient failure logs to
    `alert_escalations` (failed_at + error) so the customer portal
    shows partial delivery.
    """
    if context.severity == "green":
        return  # Not an alert — defensive.

    email_sender = email_sender or _build_email_sender()
    sms_sender = sms_sender or _build_sms_sender()
    fcm_sender = fcm_sender or _build_fcm_sender()

    async with AsyncSessionLocal() as db:
        store_repo = StoreRepository(db)
        store = await store_repo.get_by_id(context.store_id) if context.store_id else None
        if not store:
            logger.warning(
                "escalation_store_not_found",
                extra={"alert_id": context.alert_id, "store_id": context.store_id},
            )
            return
        store_name = store.get("name") or "—"
        stored_settings = store.get("settings")
        store_settings = resolve_settings(stored_settings)

        tg_rows = await TelegramSubscriberRepository(db).list_for_store(
            context.store_id
        )
        telegram_chat_ids = [r["chat_id"] for r in tg_rows]
        if not telegram_chat_ids and store.get("telegram_chat_id"):
            telegram_chat_ids = [store["telegram_chat_id"]]

        push_rows = await PushTokenRepository(db).list_for_store(context.store_id)
        escalation_repo = AlertEscalationRepository(db)

        camera_name = f"Camera #{context.camera_id}" if context.camera_id else "—"

        # --- Telegram fan-out (yellow/orange/red) --------------------
        if telegram_notifier.is_configured:
            for chat_id in telegram_chat_ids:
                try:
                    await telegram_notifier.send_alert(
                        chat_id=chat_id,
                        store_name=store_name,
                        camera_name=camera_name,
                        reason=context.reason,
                        image_path=context.image_path,
                        score=context.score,
                        severity=context.severity,
                        alert_id=context.alert_id,
                    )
                    await escalation_repo.log_delivery(
                        alert_id=context.alert_id,
                        channel="telegram",
                        recipient=chat_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "escalation_telegram_failed",
                        extra={"chat_id": chat_id, "error": str(exc)},
                    )
                    await escalation_repo.log_failure(
                        alert_id=context.alert_id,
                        channel="telegram",
                        recipient=chat_id,
                        error=str(exc),
                    )

        # --- Email fan-out (yellow/orange/red) -----------------------
        email_targets = _email_targets(store_settings)
        for language, addr in email_targets:
            try:
                subject = build_email_subject(
                    store_name=store_name, severity=context.severity, language=language
                )
                text_body, html_body = build_email_bodies(
                    store_name=store_name,
                    camera_name=camera_name,
                    reason=context.reason,
                    score=context.score,
                    severity=context.severity,
                    language=language,
                )
                await email_sender.send(
                    OutgoingEmail(
                        to=addr,
                        subject=subject,
                        text_body=text_body,
                        html_body=html_body,
                    )
                )
                await escalation_repo.log_delivery(
                    alert_id=context.alert_id,
                    channel="email",
                    recipient=addr,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "escalation_email_failed",
                    extra={"to": addr, "error": str(exc)},
                )
                await escalation_repo.log_failure(
                    alert_id=context.alert_id,
                    channel="email",
                    recipient=addr,
                    error=str(exc),
                )

        # --- FCM fan-out (orange/red only) ---------------------------
        if context.severity in ("orange", "red") and fcm_sender is not None:
            for row in push_rows:
                token = row.get("token")
                if not token:
                    continue
                try:
                    payload = build_fcm_payload(
                        store_name=store_name,
                        camera_name=camera_name,
                        severity=context.severity,
                        alert_id=context.alert_id,
                    )
                    await fcm_sender.send(
                        OutgoingPush(
                            token=token,
                            title=payload["notification"]["title"],
                            body=payload["notification"]["body"],
                            data=payload["data"],
                        )
                    )
                    await escalation_repo.log_delivery(
                        alert_id=context.alert_id,
                        channel="fcm",
                        recipient=token[:16],  # don't log full token
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "escalation_fcm_failed",
                        extra={"token_prefix": token[:8], "error": str(exc)},
                    )
                    await escalation_repo.log_failure(
                        alert_id=context.alert_id,
                        channel="fcm",
                        recipient=token[:16],
                        error=str(exc),
                    )

        # --- SMS fan-out (red only, rate-limited) --------------------
        if context.severity == "red" and sms_sender is not None:
            sms_numbers = store_settings.notification_channels.sms.numbers
            tenant_scope = context.tenant_id or str(context.store_id)
            for phone in sms_numbers:
                if _sms_rate_limited(tenant_scope, phone):
                    await escalation_repo.log_failure(
                        alert_id=context.alert_id,
                        channel="sms",
                        recipient=phone,
                        error="rate_limited: 1/5min/chat",
                    )
                    continue
                try:
                    body = build_sms_body(
                        store_name=store_name, severity=context.severity
                    )
                    await sms_sender.send(OutgoingSms(to=phone, body=body))
                    await escalation_repo.log_delivery(
                        alert_id=context.alert_id,
                        channel="sms",
                        recipient=phone,
                    )
                except SmsUnavailableError as exc:
                    logger.warning(
                        "escalation_sms_provider_outage",
                        extra={"error": str(exc)},
                    )
                    await escalation_repo.log_failure(
                        alert_id=context.alert_id,
                        channel="sms",
                        recipient=phone,
                        error=f"provider_outage: {exc}",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "escalation_sms_failed",
                        extra={"phone": phone, "error": str(exc)},
                    )
                    await escalation_repo.log_failure(
                        alert_id=context.alert_id,
                        channel="sms",
                        recipient=phone,
                        error=str(exc),
                    )


def _email_targets(store_settings: StoreSettings) -> list[tuple[str, str]]:
    """Return [(language, email_address), ...]. Defaults every address
    to Mongolian — a per-subscriber language column is T5-13 work."""
    addrs = store_settings.notification_channels.email.addresses
    return [("mn", a) for a in addrs if a]


__all__ = [
    "AlertContext",
    "SMS_RATE_LIMIT_WINDOW_S",
    "dispatch_alert",
]

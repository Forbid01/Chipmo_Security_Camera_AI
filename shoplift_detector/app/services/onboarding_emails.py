"""7-day onboarding email sequence (T2-08).

Each entry in `EMAIL_SCHEDULE` is a Day-N trigger: on the cron's
daily tick we look at every active-trial tenant whose age (in whole
days since signup) matches an entry they haven't received yet, and
dispatch the Mongolian template.

Send history is tracked via `audit_log` with action
`onboarding_email_sent` + `details.day` — no new column on tenants,
so the feature ships without another migration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from app.db.models.audit_log import AUDIT_ACTIONS
from app.db.repository.audit_log import AuditLogRepository
from app.services.email_sender import EmailSender, OutgoingEmail
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ONBOARDING_EMAIL_ACTION = "onboarding_email_sent"
AUDIT_ACTIONS.setdefault(ONBOARDING_EMAIL_ACTION, ONBOARDING_EMAIL_ACTION)


# ---------------------------------------------------------------------------
# Template builders — one per day, each returns an `OutgoingEmail`
# ---------------------------------------------------------------------------

def _store_greeting(tenant: dict[str, Any]) -> str:
    name = tenant.get("display_name") or tenant.get("legal_name")
    return f"Сайн уу, {name}!" if name else "Сайн уу!"


def _base_email(tenant: dict[str, Any], subject: str, body: str) -> OutgoingEmail:
    return OutgoingEmail(
        to=tenant["email"],
        subject=subject,
        text_body=body,
        html_body=f"<div style='font-family:sans-serif'>{body}</div>".replace(
            "\n", "<br>"
        ),
    )


def _telegram_bot_link(tenant: dict[str, Any]) -> str:
    return f"https://t.me/sentry_bot?start={tenant['tenant_id']}"


def day_0_welcome(tenant: dict[str, Any]) -> OutgoingEmail:
    greeting = _store_greeting(tenant)
    telegram_link = _telegram_bot_link(tenant)
    body = (
        f"🎉 {greeting}\n\n"
        "Sentry-д тавтай морил! Дараах 14 хоногт та манай бүх функцийг "
        "үнэгүй туршиж үзэх боломжтой.\n\n"
        "Эхний алхам:\n"
        "  1. Docker agent суулгах\n"
        "  2. Камераа холбох\n"
        "  3. Анхны хулгайч илрүүлэхийг хүлээх\n"
        f"  4. Telegram bot-оо холбох: {telegram_link}\n\n"
        "Ямар нэг асуудал тулгарвал Telegram-ийн @sentry_support рүү бичээрэй."
    )
    return _base_email(tenant, "🎉 Sentry-д тавтай морил!", body)


def day_1_check_first_detection(tenant: dict[str, Any]) -> OutgoingEmail:
    body = (
        f"{_store_greeting(tenant)}\n\n"
        "Анхны хүний илрүүлэлт амжилттай болсон уу?\n\n"
        "Хэрэв Docker agent суулгаж, камер холбосон бол одоо dashboard дээр "
        "live preview харагдах ёстой.\n\n"
        "Холболтын алдаа гарвал:\n"
        "  • RTSP URL-аа дахин шалгаарай\n"
        "  • Камер-сүлжээний ping тест хийх\n"
        "  • Туслалцаа хэрэгтэй бол → help@sentry.mn"
    )
    return _base_email(tenant, "Анхны detect хийсэн үү?", body)


def day_2_telegram_bot(tenant: dict[str, Any]) -> OutgoingEmail:
    body = (
        f"{_store_greeting(tenant)}\n\n"
        "Telegram bot-той холбогдсон уу? Live alert-ыг утсан дээрээ шууд "
        "авах хамгийн хурдан арга.\n\n"
        "Холбох:\n"
        "  1. Telegram дээр @sentry_alerts_bot хайх\n"
        "  2. /start дараад дэлгүүрийнхээ tenant_id оруулах\n"
        "  3. Manager-ийн багаа мөн урих"
    )
    return _base_email(tenant, "Telegram bot холбох зааварчилгаа", body)


def day_3_camera_placement(tenant: dict[str, Any]) -> OutgoingEmail:
    body = (
        f"{_store_greeting(tenant)}\n\n"
        "Камерын байрлалын сайн туршлага:\n\n"
        "  ✅ Орц-гарц дээр pair-аар тавих (front + side angle)\n"
        "  ✅ Бараа-ны лангуу дээр 2.5-3м өндөр\n"
        "  ✅ Кассны талаас хүний биеийг харуулсан өнцөг\n"
        "  ❌ Өндөрт доош харсан — pose detection буурдаг\n"
        "  ❌ Лангуу дундуур — хаалтан дахь хөдөлгөөн мисс болдог\n\n"
        "Видео зааварчилгаа: sentry.mn/docs/placement"
    )
    return _base_email(tenant, "Дэлгүүрийн зураглал зурах", body)


def day_5_false_alarm_feedback(tenant: dict[str, Any]) -> OutgoingEmail:
    body = (
        f"{_store_greeting(tenant)}\n\n"
        "False alarm болгоныг бидэнд мэдэгдэх нь AI-г таны дэлгүүрийн "
        "онцлогт тааруулж сургадаг.\n\n"
        "Alert card дээрх:\n"
        "  👍 Зөв илрүүлсэн\n"
        "  👎 Ташаа дохио\n"
        "  🤔 Шалгах шаардлагатай\n\n"
        "20+ feedback цугларсны дараа дэлгүүр тус бүрт тохирсон threshold "
        "+ action weights автоматаар тохируулагдана."
    )
    return _base_email(tenant, "False alarm-ыг мэдэгдэх нь яагаад чухал вэ?", body)


def day_7_first_week_report(tenant: dict[str, Any]) -> OutgoingEmail:
    body = (
        f"{_store_greeting(tenant)}\n\n"
        "Таны эхний 7 хоногийн ажиглалт dashboard дээр бэлэн боллоо!\n\n"
        "Харах:\n"
        "  📊 Өдрийн/цагийн зочин тоо\n"
        "  🚨 Нийт alert + severity breakdown\n"
        "  ⏱  Average response time\n"
        "  🎯 Precision / recall estimate\n\n"
        "Тайлангаа татах: sentry.mn/reports/weekly"
    )
    return _base_email(tenant, "Анхны 7 хоногийн тайлан", body)


def day_12_trial_ending_soon(tenant: dict[str, Any]) -> OutgoingEmail:
    body = (
        f"{_store_greeting(tenant)}\n\n"
        "Trial 2 хоногийн дараа дуусна. Сэтгэл нийцсэн бол subscription-аа "
        "идэвхжүүлээрэй — таны бүх тохиргоо, feedback, тайлан хадгалагдах "
        "болно.\n\n"
        "Өнөөдөр субскрайб хийвэл:\n"
        "  • Эхний сарын төлбөр дотроо 30-хоног баталгаатай буцаалт\n"
        "  • Жилээр төлвөл 10% хямдрал\n\n"
        "Plan-аа сонгох: sentry.mn/billing"
    )
    return _base_email(tenant, "Trial дуусахад 2 хоног үлдлээ", body)


# ---------------------------------------------------------------------------
# Schedule — day → builder
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScheduledEmail:
    day: int
    builder: Callable[[dict[str, Any]], OutgoingEmail]
    label: str


EMAIL_SCHEDULE: tuple[ScheduledEmail, ...] = (
    ScheduledEmail(0, day_0_welcome, "welcome"),
    ScheduledEmail(1, day_1_check_first_detection, "first_detection_nudge"),
    ScheduledEmail(2, day_2_telegram_bot, "telegram_bot"),
    ScheduledEmail(3, day_3_camera_placement, "camera_placement"),
    ScheduledEmail(5, day_5_false_alarm_feedback, "false_alarm_feedback"),
    ScheduledEmail(7, day_7_first_week_report, "week_one_report"),
    ScheduledEmail(12, day_12_trial_ending_soon, "trial_ending"),
)


# ---------------------------------------------------------------------------
# Scheduler — decides which emails are due today + dispatches
# ---------------------------------------------------------------------------

def _days_since_signup(tenant: dict[str, Any], now: datetime) -> int:
    created = tenant.get("created_at")
    if created is None:
        return 0
    # `created_at` from the repo is tz-aware; coerce both to UTC dates.
    return (now.date() - created.date()).days


def due_for_tenant(
    tenant: dict[str, Any],
    *,
    already_sent_days: frozenset[int],
    now: datetime | None = None,
) -> list[ScheduledEmail]:
    """Return every schedule entry whose day-number matches the
    tenant's age and hasn't already been dispatched.

    Sending is single-pass — if the cron missed Day 2, Day 5 still
    fires on schedule, but Day 2 is skipped (we don't spam old
    emails three days late).
    """
    now = now or datetime.now(UTC)
    age = _days_since_signup(tenant, now)
    return [
        entry
        for entry in EMAIL_SCHEDULE
        if entry.day == age and entry.day not in already_sent_days
    ]


async def _already_sent_days(
    db: AsyncSession, tenant_id: Any
) -> frozenset[int]:
    """Read the audit_log for this tenant's onboarding-email history."""
    query = text("""
        SELECT details
          FROM audit_log
         WHERE action = :action
           AND resource_type = 'tenant'
           AND resource_uuid = CAST(:tenant_id AS UUID)
    """)
    result = await db.execute(
        query,
        {"action": ONBOARDING_EMAIL_ACTION, "tenant_id": str(tenant_id)},
    )
    days: set[int] = set()
    for row in result.mappings().fetchall():
        details = row.get("details") or {}
        # PostgreSQL JSONB → asyncpg returns dict, but sometimes a str.
        if isinstance(details, str):
            import json
            try:
                details = json.loads(details)
            except Exception:
                continue
        day = details.get("day")
        if isinstance(day, int):
            days.add(day)
    return frozenset(days)


async def dispatch_due_emails(
    db: AsyncSession,
    *,
    tenant: dict[str, Any],
    email_sender: EmailSender,
    now: datetime | None = None,
) -> list[str]:
    """Fire every schedule entry due for this tenant. Returns the
    labels actually dispatched so callers can log / meter delivery.
    """
    sent_days = await _already_sent_days(db, tenant["tenant_id"])
    due = due_for_tenant(tenant, already_sent_days=sent_days, now=now)
    if not due:
        return []

    audit_repo = AuditLogRepository(db)
    dispatched: list[str] = []
    for entry in due:
        message = entry.builder(tenant)
        try:
            await email_sender.send(message)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "onboarding_email_send_failed",
                extra={
                    "tenant_id": str(tenant["tenant_id"]),
                    "day": entry.day,
                    "error": str(exc),
                },
            )
            continue
        await audit_repo.log(
            action=ONBOARDING_EMAIL_ACTION,
            user_id=None,
            resource_type="tenant",
            resource_uuid=tenant["tenant_id"],
            details={"day": entry.day, "label": entry.label},
        )
        dispatched.append(entry.label)
    await db.commit()
    return dispatched


async def run_onboarding_email_cron(
    db: AsyncSession,
    *,
    email_sender: EmailSender,
    now: datetime | None = None,
) -> dict[str, list[str]]:
    """Scheduler entrypoint — iterates every trial-active tenant and
    dispatches whatever is due for them today. Returns a map of
    tenant_id → delivered labels for observability.
    """
    now = now or datetime.now(UTC)
    # Only touch tenants within the 14-day trial window + a short
    # tail. Day 12 is the latest scheduled send; anything older is
    # out of scope for this cron.
    window_days = max(e.day for e in EMAIL_SCHEDULE) + 1
    cutoff = now - timedelta(days=window_days)
    query = text("""
        SELECT tenant_id, legal_name, display_name, email, created_at
          FROM tenants
         WHERE status = 'active'
           AND plan = 'trial'
           AND created_at >= :cutoff
    """)
    result = await db.execute(query, {"cutoff": cutoff})
    out: dict[str, list[str]] = {}
    for row in result.mappings().fetchall():
        tenant = dict(row)
        labels = await dispatch_due_emails(
            db, tenant=tenant, email_sender=email_sender, now=now
        )
        if labels:
            out[str(tenant["tenant_id"])] = labels
    return out


__all__ = [
    "ONBOARDING_EMAIL_ACTION",
    "EMAIL_SCHEDULE",
    "ScheduledEmail",
    "due_for_tenant",
    "dispatch_due_emails",
    "run_onboarding_email_cron",
]

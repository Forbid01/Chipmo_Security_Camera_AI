"""Telegram bot command dispatcher (T5-03).

Handles inbound slash commands sent to the bot by store managers.
Routes each command to a pure async handler that takes the parsed
command + chat_id and returns the reply text. The webhook endpoint
(`POST /api/v1/telegram/webhook`) calls `dispatch_update` with the
raw Telegram Update dict.

Design notes:

* **No python-telegram-bot.** The production notifier already speaks
  raw HTTP via httpx; pulling in a second bot framework that wants
  its own event loop would churn more than it buys. If the dispatch
  table grows past ~10 commands we revisit.
* **Per-handler DB session.** Each handler opens its own
  AsyncSessionLocal so a slow query on one command can't starve
  another webhook delivery.
* **Reply is always produced.** Even unknown commands get a reply
  pointing at `/help`. Silent-failure bots are harder to debug than
  noisy ones.
* **Fail-closed auth.** If the incoming update doesn't carry a
  `message.chat.id`, the dispatcher returns early — no speculative
  lookups, no cross-chat leakage.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.db.repository.alerts import AlertRepository
from app.db.repository.telegram_subscribers import TelegramSubscriberRepository
from app.db.session import AsyncSessionLocal
from app.services.telegram_notifier import ACK_CALLBACK_PREFIX, telegram_notifier

logger = logging.getLogger(__name__)


CommandHandler = Callable[[str, str], Awaitable[str]]


HELP_TEXT = (
    "<b>Chipmo Security Bot</b>\n\n"
    "Ашиглах боломжтой командууд:\n"
    "/start — танилцуулга\n"
    "/status — миний дэлгүүрүүдийн төлөв\n"
    "/today — өнөөдрийн сэрэмжлүүлгүүд\n"
    "/alerts — сүүлийн 5 сэрэмжлүүлэг\n"
    "/help — энэ жагсаалт"
)


async def _start(chat_id: str, _args: str) -> str:
    return (
        "👋 Sentry Security Bot-д тавтай морил!\n\n"
        f"Таны chat ID: <code>{chat_id}</code>\n\n"
        "Энэ ID-г дэлгүүрийн админд өгч subscriber-ээр нэмүүлнэ үү. "
        "Нэмэгдсэний дараа бүх сэрэмжлүүлэг автоматаар энд ирнэ.\n\n"
        "Бусад команд: /help"
    )


async def _help(_chat_id: str, _args: str) -> str:
    return HELP_TEXT


async def _status(chat_id: str, _args: str) -> str:
    async with AsyncSessionLocal() as db:
        subscriptions = await TelegramSubscriberRepository(db).find_by_chat(chat_id)
    if not subscriptions:
        return (
            "Та одоогоор ямар ч дэлгүүрт subscribe хийгээгүй байна.\n\n"
            f"Chat ID: <code>{chat_id}</code>\n"
            "Админаар бүртгүүлээрэй."
        )
    lines = ["<b>Таны subscribe хийсэн дэлгүүрүүд:</b>", ""]
    for row in subscriptions:
        lines.append(f"• <b>{row['store_name']}</b> — {row['role']}")
    return "\n".join(lines)


async def _today(chat_id: str, _args: str) -> str:
    async with AsyncSessionLocal() as db:
        subs = await TelegramSubscriberRepository(db).find_by_chat(chat_id)
        if not subs:
            return "Та ямар ч дэлгүүрт subscribe хийгээгүй байна. /start-аас эхэл."

        store_ids = [row["store_id"] for row in subs]
        since = datetime.now(UTC) - timedelta(hours=24)
        result = await db.execute(
            text(
                """
                SELECT s.id, s.name, COUNT(a.id) AS alert_count
                FROM stores s
                LEFT JOIN alerts a
                  ON a.store_id = s.id
                  AND a.event_time >= :since
                WHERE s.id = ANY(:store_ids)
                GROUP BY s.id, s.name
                ORDER BY s.name
                """
            ),
            {"since": since, "store_ids": store_ids},
        )
        rows = result.mappings().fetchall()

    lines = ["<b>Сүүлийн 24 цагийн сэрэмжлүүлэг:</b>", ""]
    total = 0
    for row in rows:
        count = row["alert_count"] or 0
        total += count
        lines.append(f"• <b>{row['name']}</b>: {count}")
    lines.append("")
    lines.append(f"<b>Нийт:</b> {total}")
    return "\n".join(lines)


async def _alerts(chat_id: str, _args: str) -> str:
    async with AsyncSessionLocal() as db:
        subs = await TelegramSubscriberRepository(db).find_by_chat(chat_id)
        if not subs:
            return "Subscribe хийгээгүй байна. /start-аас эхэл."

        store_ids = [row["store_id"] for row in subs]
        result = await db.execute(
            text(
                """
                SELECT
                    a.id, a.event_time, a.description,
                    COALESCE(a.severity, 'green') AS severity,
                    s.name AS store_name
                FROM alerts a
                LEFT JOIN stores s ON s.id = a.store_id
                WHERE a.store_id = ANY(:store_ids)
                ORDER BY a.event_time DESC
                LIMIT 5
                """
            ),
            {"store_ids": store_ids},
        )
        rows = result.mappings().fetchall()

    if not rows:
        return "Сэрэмжлүүлэг алга байна 🎉"

    severity_icon = {"red": "🚨", "orange": "⚠️", "yellow": "👀", "green": "✅"}
    lines = ["<b>Сүүлийн 5 сэрэмжлүүлэг:</b>", ""]
    for row in rows:
        ts = row["event_time"]
        ts_str = ts.strftime("%m-%d %H:%M") if ts else "?"
        icon = severity_icon.get(row["severity"], "•")
        lines.append(
            f"{icon} <b>{row['store_name'] or '—'}</b> · {ts_str}\n"
            f"    {row['description'] or ''}"
        )
    return "\n".join(lines)


async def _unknown(_chat_id: str, _args: str) -> str:
    return f"Ойлгомжгүй команд байна.\n\n{HELP_TEXT}"


_HANDLERS: dict[str, CommandHandler] = {
    "/start": _start,
    "/help": _help,
    "/status": _status,
    "/today": _today,
    "/alerts": _alerts,
}


def _parse_command(text_value: str) -> tuple[str, str]:
    """Split an incoming message into (command, args).

    Telegram commands may include a bot suffix (`/start@sentry_bot`);
    we strip it so handlers can match on the bare slash-command.
    Returns (None-equivalent, "") for non-command messages.
    """
    trimmed = (text_value or "").strip()
    if not trimmed.startswith("/"):
        return "", trimmed
    head, _, rest = trimmed.partition(" ")
    command = head.split("@", 1)[0].lower()
    return command, rest.strip()


async def handle_update(update: dict[str, Any]) -> None:
    """Webhook entry point — parse, dispatch, reply.

    Never raises: the webhook endpoint treats any exception as
    'processed' so Telegram doesn't retry the same update forever.
    Two input shapes:

    * `message` / `edited_message` — slash-command dispatch.
    * `callback_query` — inline-button ack (T5-05).
    """
    if "callback_query" in update:
        await _handle_callback_query(update["callback_query"])
        return

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text_value = message.get("text") or ""

    if chat_id is None:
        # Non-message updates (channel posts, etc). Ignore cleanly.
        return

    chat_id_str = str(chat_id)
    command, args = _parse_command(text_value)
    if not command:
        return  # plain messages — no dispatch

    handler = _HANDLERS.get(command, _unknown)
    try:
        reply = await handler(chat_id_str, args)
    except Exception:
        logger.exception("telegram_bot_handler_failed", extra={"command": command})
        reply = "Серверийн алдаа гарлаа. Дахин оролдоно уу."

    await telegram_notifier.send_message(chat_id_str, reply)


async def _handle_callback_query(query: dict[str, Any]) -> None:
    """T5-05 — handle the inline 'Анхааралаа авлаа' button.

    Contract:

    * `callback_data` looks like `ack:{alert_id}`. Unknown prefixes
      answer with a generic ack so Telegram's spinner clears, but
      no DB mutation happens.
    * Idempotent: if the alert is already acknowledged (by this or
      another chat), we tell the user who got there first and remove
      the button on this message. Double-tap never corrupts state.
    * Button removal uses `editMessageReplyMarkup` with no markup —
      safe even if the message came from a different chat than the
      clicker (inline keyboards are per-message).
    """
    query_id = query.get("id")
    data = query.get("data") or ""
    from_user = query.get("from") or {}
    from_chat_id = str(from_user.get("id") or "")
    message = query.get("message") or {}
    message_chat_id = str((message.get("chat") or {}).get("id") or "")
    message_id = message.get("message_id")

    if not query_id or not data.startswith(ACK_CALLBACK_PREFIX):
        # Keep Telegram happy (clear the loading spinner) but don't
        # touch any rows for an unrecognised payload.
        if query_id:
            await telegram_notifier.answer_callback_query(
                query_id, text="Ойлгомжгүй товч."
            )
        return

    raw_id = data[len(ACK_CALLBACK_PREFIX):]
    try:
        alert_id = int(raw_id)
    except ValueError:
        await telegram_notifier.answer_callback_query(
            query_id, text="Alert ID буруу формат."
        )
        return

    acker_chat_id = from_chat_id or message_chat_id

    async with AsyncSessionLocal() as db:
        repo = AlertRepository(db)
        flipped = await repo.mark_acknowledged(alert_id, chat_id=acker_chat_id)
        ack_state = await repo.get_ack_state(alert_id)

    if flipped:
        answer_text = "✅ Анхаарал авлаа"
    elif ack_state and ack_state.get("acknowledged_at"):
        # Someone else got there first — tell the user and still remove
        # the button so the UI converges to 'handled'.
        owner = ack_state.get("acknowledged_by_chat_id") or "другой"
        answer_text = f"Аль хэдийн авсан байна ({owner})"
    else:
        # Alert not found / pre-migration schema. Don't pretend
        # success; surface the ambiguity to the user.
        answer_text = "Alert олдсонгүй эсвэл схем бэлэн биш."

    await telegram_notifier.answer_callback_query(query_id, text=answer_text)

    if message_chat_id and message_id is not None:
        # Remove the inline keyboard so the button can't be pressed
        # again from this message. Other subscribers' copies stay as
        # they are — they'll see the "аль хэдийн авсан" reply if they
        # click. An editMessageReplyMarkup failure is non-fatal
        # (e.g. message too old to edit).
        await telegram_notifier.edit_message_reply_markup(
            chat_id=message_chat_id,
            message_id=int(message_id),
            reply_markup=None,
        )


__all__ = [
    "HELP_TEXT",
    "handle_update",
]

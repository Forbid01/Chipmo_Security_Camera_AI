"""Telegram мэдэгдэл илгээх сервис.

Дэлгүүр бүрт бүртгэсэн telegram_chat_id руу
alert илэрмэгц зураг + мэдэгдэл илгээнэ.
"""

import json
import logging

import httpx

logger = logging.getLogger(__name__)


# T5-05 — inline callback prefix. Stays short because Telegram caps
# callback_data at 64 bytes and we want room for the alert_id.
ACK_CALLBACK_PREFIX = "ack:"


def build_ack_keyboard(alert_id: int) -> dict:
    """Inline keyboard with a single 'Анхааралаа авлаа' button.

    Callback payload format: `ack:{alert_id}`. The webhook dispatcher
    splits on the colon and UPDATEs `alerts.acknowledged_at`.
    """
    return {
        "inline_keyboard": [[
            {
                "text": "✅ Анхааралаа авлаа",
                "callback_data": f"{ACK_CALLBACK_PREFIX}{alert_id}",
            }
        ]]
    }


# Per-severity emoji for the Telegram channel. Header *text* comes
# from `alert_copy.severity_header` so every channel agrees on the
# Mongolian wording + is covered by the T5-11 lint test. If a new
# severity lands, add it here and in alert_copy; missing emoji falls
# back to orange.
_SEVERITY_EMOJI: dict[str, str] = {
    "red": "🚨",
    "orange": "⚠️",
    "yellow": "👀",
}


def _severity_header(severity: str | None) -> tuple[str, str]:
    """Pick the Mongolian header + emoji for a severity tier.

    Unknown / None falls through to the orange copy so a caller that
    forgets to pass severity still gets a sensible message.
    """
    # Lazy import breaks a cycle: alert_copy must not import the
    # notifier (it's pure copy, no I/O), but the notifier needs the
    # shared header table so both channels agree.
    from app.services.alert_copy import severity_header

    key = (severity or "").lower()
    if key not in _SEVERITY_EMOJI:
        key = "orange"
    return (severity_header(key, "mn"), _SEVERITY_EMOJI[key])


class TelegramNotifier:
    def __init__(self):
        self._bot_token: str | None = None

    def configure(self, bot_token: str | None):
        self._bot_token = bot_token
        if bot_token:
            logger.info("Telegram notifier configured.")
        else:
            logger.warning("Telegram bot token not set — notifications disabled.")

    @property
    def is_configured(self) -> bool:
        return bool(self._bot_token)

    async def send_alert(
        self,
        chat_id: str,
        store_name: str,
        camera_name: str,
        reason: str,
        image_path: str | None = None,
        score: float | None = None,
        severity: str | None = None,
        alert_id: int | None = None,
    ):
        """Alert-ийг Telegram руу илгээх.

        T5-05: when `alert_id` is supplied, attach an inline keyboard
        with a single "Ack" button whose callback_data encodes the
        alert_id. The webhook dispatcher picks that up and marks the
        row acknowledged.
        """
        if not self._bot_token or not chat_id:
            return

        score_text = f"Score: {score:.0f}" if score else ""
        header, icon = _severity_header(severity)
        text = (
            f"{icon} <b>{header}</b>\n\n"
            f"🏪 <b>{store_name}</b>\n"
            f"📹 {camera_name}\n"
            f"📋 {reason}\n"
            f"{score_text}"
        )
        reply_markup = build_ack_keyboard(alert_id) if alert_id else None

        url = f"https://api.telegram.org/bot{self._bot_token}"
        # reply_markup must be a JSON string when sent as form-data;
        # the json-bodied sendMessage path accepts the native dict.
        reply_markup_str = (
            json.dumps(reply_markup) if reply_markup is not None else None
        )

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if image_path and isinstance(image_path, str) and image_path.startswith(("http://", "https://")):
                    data = {
                        "chat_id": chat_id,
                        "caption": text,
                        "parse_mode": "HTML",
                        "photo": image_path,
                    }
                    if reply_markup_str:
                        data["reply_markup"] = reply_markup_str
                    resp = await client.post(f"{url}/sendPhoto", data=data)
                elif image_path:
                    with open(image_path, "rb") as photo:
                        data = {"chat_id": chat_id, "caption": text, "parse_mode": "HTML"}
                        if reply_markup_str:
                            data["reply_markup"] = reply_markup_str
                        resp = await client.post(
                            f"{url}/sendPhoto",
                            data=data,
                            files={"photo": ("alert.jpg", photo, "image/jpeg")},
                        )
                else:
                    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
                    if reply_markup is not None:
                        payload["reply_markup"] = reply_markup
                    resp = await client.post(f"{url}/sendMessage", json=payload)

                if resp.status_code != 200:
                    logger.error(f"Telegram error: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str | None = "HTML",
    ) -> bool:
        """Plain text reply — used by the bot command handlers (T5-03).

        Returns True on HTTP 200, False otherwise. Never raises so the
        webhook handler can process the next update even if one reply
        fails (user blocked the bot, rate-limited, etc.).
        """
        if not self._bot_token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload: dict = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.warning(
                        "telegram_send_message_failed",
                        extra={"status": resp.status_code, "chat_id": chat_id},
                    )
                return resp.status_code == 200
        except Exception as exc:
            logger.error(f"Telegram send_message error: {exc}")
            return False

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        """Telegram requires answering every callback_query so the
        client's spinner clears. We always call this — with or without
        user-facing text — as the first side-effect of a callback."""
        if not self._bot_token or not callback_query_id:
            return False
        url = f"https://api.telegram.org/bot{self._bot_token}/answerCallbackQuery"
        payload: dict = {"callback_query_id": callback_query_id}
        if text is not None:
            # Telegram caps callback answers at 200 chars.
            payload["text"] = text[:200]
        if show_alert:
            payload["show_alert"] = True
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as exc:
            logger.error(f"answer_callback_query failed: {exc}")
            return False

    async def edit_message_reply_markup(
        self,
        chat_id: str,
        message_id: int,
        reply_markup: dict | None = None,
    ) -> bool:
        """Remove or replace the inline keyboard on an already-sent
        message. Used after ack so the button can't be pressed twice."""
        if not self._bot_token:
            return False
        url = f"https://api.telegram.org/bot{self._bot_token}/editMessageReplyMarkup"
        payload: dict = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as exc:
            logger.error(f"edit_message_reply_markup failed: {exc}")
            return False

    async def send_test(self, chat_id: str) -> bool:
        """Тест мэдэгдэл илгээх — тохиргоо шалгах зориулалттай."""
        if not self._bot_token or not chat_id:
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        text = "✅ Chipmo Security AI холбогдлоо!\nТа энэ чатаар мэдэгдэл хүлээн авна."

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram test failed: {e}")
            return False


# Singleton
telegram_notifier = TelegramNotifier()

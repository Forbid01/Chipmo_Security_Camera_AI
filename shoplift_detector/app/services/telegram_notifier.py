"""Telegram мэдэгдэл илгээх сервис.

Дэлгүүр бүрт бүртгэсэн telegram_chat_id руу
alert илэрмэгц зураг + мэдэгдэл илгээнэ.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


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
    ):
        """Alert-ийг Telegram руу илгээх."""
        if not self._bot_token or not chat_id:
            return

        score_text = f"Score: {score:.0f}" if score else ""
        text = (
            f"🚨 <b>Анхааруулга!</b>\n\n"
            f"🏪 <b>{store_name}</b>\n"
            f"📹 {camera_name}\n"
            f"📋 {reason}\n"
            f"{score_text}"
        )

        url = f"https://api.telegram.org/bot{self._bot_token}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if image_path and isinstance(image_path, str) and image_path.startswith(("http://", "https://")):
                    resp = await client.post(
                        f"{url}/sendPhoto",
                        data={
                            "chat_id": chat_id,
                            "caption": text,
                            "parse_mode": "HTML",
                            "photo": image_path,
                        },
                    )
                elif image_path:
                    with open(image_path, "rb") as photo:
                        resp = await client.post(
                            f"{url}/sendPhoto",
                            data={"chat_id": chat_id, "caption": text, "parse_mode": "HTML"},
                            files={"photo": ("alert.jpg", photo, "image/jpeg")},
                        )
                else:
                    resp = await client.post(
                        f"{url}/sendMessage",
                        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                    )

                if resp.status_code != 200:
                    logger.error(f"Telegram error: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

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

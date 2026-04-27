"""Unit tests for the T5-03 Telegram bot command dispatcher.

Covers pure parsing + dispatch routing + secret-token enforcement. DB
lookups (`/status`, `/today`, `/alerts`) are exercised separately
through the repository tests — we mock the DB at the session factory
so these tests stay fast and hermetic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-bot")

from app.services.telegram_bot import (  # noqa: E402
    HELP_TEXT,
    _parse_command,
    handle_update,
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("incoming,expected_cmd,expected_args", [
    ("/start", "/start", ""),
    ("/help", "/help", ""),
    ("/status some extra", "/status", "some extra"),
    ("  /today   ", "/today", ""),
    ("/start@sentry_bot", "/start", ""),
    ("/alerts@SomeBot arg1 arg2", "/alerts", "arg1 arg2"),
    ("hello world", "", "hello world"),
    ("", "", ""),
])
def test_parse_command(incoming, expected_cmd, expected_args):
    cmd, args = _parse_command(incoming)
    assert cmd == expected_cmd
    assert args == expected_args


# ---------------------------------------------------------------------------
# Dispatch — /start, /help, unknown
# ---------------------------------------------------------------------------

def _update(text_value: str, chat_id: int = 12345) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id, "type": "private"},
            "text": text_value,
        },
    }


@pytest.mark.asyncio
async def test_start_replies_with_chat_id(monkeypatch):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **_kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        fake_send,
    )
    await handle_update(_update("/start"))

    assert len(sent) == 1
    chat_id, reply = sent[0]
    assert chat_id == "12345"
    assert "12345" in reply
    assert "Sentry Security Bot" in reply


@pytest.mark.asyncio
async def test_help_returns_command_list(monkeypatch):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **_kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        fake_send,
    )
    await handle_update(_update("/help"))
    assert sent[0][1] == HELP_TEXT


@pytest.mark.asyncio
async def test_unknown_command_points_to_help(monkeypatch):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **_kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        fake_send,
    )
    await handle_update(_update("/nope"))
    assert "Ойлгомжгүй команд" in sent[0][1]
    assert "/help" in sent[0][1]


@pytest.mark.asyncio
async def test_non_message_updates_ignored(monkeypatch):
    """Channel posts / callback queries shouldn't trigger a reply."""
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **_kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        fake_send,
    )
    # No `message` key — Telegram sent a `callback_query` or similar.
    await handle_update({"update_id": 7, "callback_query": {"id": "x"}})
    assert sent == []


@pytest.mark.asyncio
async def test_plain_text_no_reply(monkeypatch):
    """Non-command messages are ignored (we're not a chat bot)."""
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **_kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        fake_send,
    )
    await handle_update(_update("hello bot"))
    assert sent == []


@pytest.mark.asyncio
async def test_handler_exception_surfaces_as_server_error(monkeypatch):
    """A handler that raises must not kill the webhook — the user sees
    a generic error message, the exception gets logged."""
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **_kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        fake_send,
    )

    async def exploding(_chat_id, _args):
        raise RuntimeError("db is down")

    monkeypatch.setitem(
        __import__("app.services.telegram_bot", fromlist=["_HANDLERS"])._HANDLERS,
        "/status",
        exploding,
    )

    await handle_update(_update("/status"))
    assert len(sent) == 1
    assert "Серверийн алдаа" in sent[0][1]


# ---------------------------------------------------------------------------
# Webhook endpoint — secret enforcement
# ---------------------------------------------------------------------------

@pytest.fixture
def webhook_app(monkeypatch):
    from app.api.v1.telegram import router
    from fastapi import FastAPI

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "shhh")

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/telegram")
    return app


def test_webhook_rejects_wrong_secret(webhook_app, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        AsyncMock(return_value=True),
    )
    client = TestClient(webhook_app)
    resp = client.post(
        "/api/v1/telegram/webhook",
        json=_update("/start"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert resp.status_code == 401


def test_webhook_accepts_correct_secret(webhook_app, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.send_message",
        AsyncMock(return_value=True),
    )
    client = TestClient(webhook_app)
    resp = client.post(
        "/api/v1/telegram/webhook",
        json=_update("/start"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "shhh"},
    )
    assert resp.status_code == 204


def test_webhook_rejects_non_json_body(webhook_app):
    from fastapi.testclient import TestClient

    client = TestClient(webhook_app)
    resp = client.post(
        "/api/v1/telegram/webhook",
        content=b"not json",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": "shhh",
            "Content-Type": "application/octet-stream",
        },
    )
    assert resp.status_code == 400

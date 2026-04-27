"""T5-05 — Telegram inline-ack callback flow.

Covers the keyboard builder (pure), the notifier's callback-query
helpers (monkeypatched httpx), and the bot dispatcher's end-to-end
callback handling (mocked DB + notifier).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-ack")

from app.services.telegram_notifier import (  # noqa: E402
    ACK_CALLBACK_PREFIX,
    build_ack_keyboard,
)


# ---------------------------------------------------------------------------
# Keyboard builder
# ---------------------------------------------------------------------------

def test_build_ack_keyboard_shape():
    kb = build_ack_keyboard(42)
    assert kb == {
        "inline_keyboard": [[
            {"text": "✅ Анхааралаа авлаа", "callback_data": "ack:42"}
        ]]
    }


def test_callback_data_under_telegram_64_byte_cap():
    """Telegram caps callback_data at 64 bytes. Even with a very large
    alert_id (10-digit), our payload stays well under the limit."""
    kb = build_ack_keyboard(9_999_999_999)
    data = kb["inline_keyboard"][0][0]["callback_data"]
    assert len(data.encode("utf-8")) <= 64
    assert data.startswith(ACK_CALLBACK_PREFIX)


# ---------------------------------------------------------------------------
# Callback-query dispatch
# ---------------------------------------------------------------------------

def _callback_update(
    *,
    data: str = "ack:42",
    query_id: str = "cq-1",
    from_chat_id: int = 1001,
    message_chat_id: int = 1001,
    message_id: int = 777,
) -> dict:
    return {
        "update_id": 1,
        "callback_query": {
            "id": query_id,
            "data": data,
            "from": {"id": from_chat_id},
            "message": {
                "message_id": message_id,
                "chat": {"id": message_chat_id, "type": "private"},
            },
        },
    }


class _StubAlertRepo:
    """Mimics AlertRepository.mark_acknowledged + get_ack_state.

    State:
      `self.acked_by` — chat_id of the first successful ack, or None.
    """

    def __init__(self, *, initial_ack_by: str | None = None):
        self.acked_by: str | None = initial_ack_by
        self.mark_calls: list[tuple[int, str]] = []

    async def mark_acknowledged(self, alert_id: int, *, chat_id: str) -> bool:
        self.mark_calls.append((alert_id, chat_id))
        if self.acked_by is None:
            self.acked_by = chat_id
            return True
        return False

    async def get_ack_state(self, _alert_id: int):
        if self.acked_by is None:
            return {"acknowledged_at": None, "acknowledged_by_chat_id": None}
        return {
            "acknowledged_at": "2026-04-24T10:00:00Z",
            "acknowledged_by_chat_id": self.acked_by,
        }


@pytest.fixture
def notifier_spy(monkeypatch):
    """Record every (method, args) call on telegram_notifier so the
    test can assert ordering without touching the network."""
    calls: list[tuple[str, dict]] = []

    async def answer(callback_query_id, *, text=None, show_alert=False):
        calls.append(("answer", {
            "id": callback_query_id, "text": text, "show_alert": show_alert
        }))
        return True

    async def edit_markup(chat_id, message_id, reply_markup=None):
        calls.append(("edit_markup", {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": reply_markup,
        }))
        return True

    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.answer_callback_query",
        answer,
    )
    monkeypatch.setattr(
        "app.services.telegram_bot.telegram_notifier.edit_message_reply_markup",
        edit_markup,
    )
    return calls


@pytest.fixture
def stub_session_factory(monkeypatch):
    """Replace AsyncSessionLocal with a context manager that yields a
    MagicMock; the alert repo is stubbed separately so the stub's
    state is what matters."""
    class _CM:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(
        "app.services.telegram_bot.AsyncSessionLocal", _CM
    )


def _patch_repo(monkeypatch, repo: _StubAlertRepo):
    monkeypatch.setattr(
        "app.services.telegram_bot.AlertRepository",
        lambda _db: repo,
    )


@pytest.mark.asyncio
async def test_ack_happy_path_flips_state_and_removes_button(
    notifier_spy, stub_session_factory, monkeypatch
):
    from app.services.telegram_bot import handle_update

    repo = _StubAlertRepo()
    _patch_repo(monkeypatch, repo)

    await handle_update(_callback_update(data="ack:42"))

    # State transition recorded.
    assert repo.mark_calls == [(42, "1001")]
    assert repo.acked_by == "1001"

    # User feedback + button removal.
    methods = [c[0] for c in notifier_spy]
    assert methods == ["answer", "edit_markup"]
    answer_args = notifier_spy[0][1]
    assert answer_args["id"] == "cq-1"
    assert "авлаа" in answer_args["text"]
    edit_args = notifier_spy[1][1]
    assert edit_args["message_id"] == 777
    assert edit_args["reply_markup"] is None


@pytest.mark.asyncio
async def test_ack_second_click_reports_prior_owner(
    notifier_spy, stub_session_factory, monkeypatch
):
    from app.services.telegram_bot import handle_update

    repo = _StubAlertRepo(initial_ack_by="9999")
    _patch_repo(monkeypatch, repo)

    await handle_update(_callback_update(data="ack:42", from_chat_id=1001))

    assert repo.acked_by == "9999", "original ack must not be overwritten"
    answer_args = notifier_spy[0][1]
    assert "Аль хэдийн" in answer_args["text"]
    assert "9999" in answer_args["text"]


@pytest.mark.asyncio
async def test_ack_unknown_prefix_no_db_mutation(
    notifier_spy, stub_session_factory, monkeypatch
):
    from app.services.telegram_bot import handle_update

    repo = _StubAlertRepo()
    _patch_repo(monkeypatch, repo)

    await handle_update(_callback_update(data="mute:42"))

    assert repo.mark_calls == []
    # Still answered the callback so the spinner clears.
    assert notifier_spy[0][0] == "answer"
    assert "Ойлгомжгүй" in notifier_spy[0][1]["text"]


@pytest.mark.asyncio
async def test_ack_malformed_id_returns_error(
    notifier_spy, stub_session_factory, monkeypatch
):
    from app.services.telegram_bot import handle_update

    repo = _StubAlertRepo()
    _patch_repo(monkeypatch, repo)

    await handle_update(_callback_update(data="ack:not-a-number"))

    assert repo.mark_calls == []
    assert "буруу формат" in notifier_spy[0][1]["text"]


# ---------------------------------------------------------------------------
# Notifier HTTP calls — answer_callback_query + edit_message_reply_markup
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = ""


class _FakeClient:
    def __init__(self, status_code: int = 200):
        self.calls: list[tuple[str, dict]] = []
        self._status = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json=None, data=None, files=None):
        self.calls.append(
            ("POST", {"url": url, "json": json, "data": data, "files": files})
        )
        return _FakeResp(self._status)


@pytest.mark.asyncio
async def test_answer_callback_query_hits_api(monkeypatch):
    from app.services import telegram_notifier as tn_mod

    tn_mod.telegram_notifier.configure("test-token")
    fake = _FakeClient(200)
    monkeypatch.setattr(
        tn_mod.httpx,
        "AsyncClient",
        lambda timeout=10: fake,
    )

    ok = await tn_mod.telegram_notifier.answer_callback_query(
        "cq-1", text="Авлаа"
    )
    assert ok is True
    assert fake.calls[0][1]["url"].endswith("/answerCallbackQuery")
    assert fake.calls[0][1]["json"]["callback_query_id"] == "cq-1"
    assert fake.calls[0][1]["json"]["text"] == "Авлаа"


@pytest.mark.asyncio
async def test_edit_reply_markup_none_clears_keyboard(monkeypatch):
    from app.services import telegram_notifier as tn_mod

    tn_mod.telegram_notifier.configure("test-token")
    fake = _FakeClient(200)
    monkeypatch.setattr(
        tn_mod.httpx,
        "AsyncClient",
        lambda timeout=10: fake,
    )

    ok = await tn_mod.telegram_notifier.edit_message_reply_markup(
        chat_id="1001", message_id=777, reply_markup=None
    )
    assert ok is True
    payload = fake.calls[0][1]["json"]
    assert payload["chat_id"] == "1001"
    assert payload["message_id"] == 777
    # No reply_markup key when explicitly clearing — Telegram treats
    # omission the same as `{"inline_keyboard": []}` for our use case.
    assert "reply_markup" not in payload

"""T5-06 / T5-07 / T5-08 / T5-09 — escalation dispatcher.

Covers the severity gating (fcm on orange+red only, sms on red only),
per-channel failure isolation, SMS rate-limit per (tenant, phone),
and that every attempt lands in `alert_escalations` via the repo.
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

os.environ.setdefault("SECRET_KEY", "test-secret-dispatch")

from app.services import escalation_dispatcher as dispatcher_mod  # noqa: E402
from app.services.email_sender import RecordingEmailSender  # noqa: E402
from app.services.escalation_dispatcher import (  # noqa: E402
    AlertContext,
    _sms_rate_limited,
    dispatch_alert,
)
from app.services.fcm_sender import RecordingFcmSender  # noqa: E402
from app.services.sms_sender import RecordingSmsSender  # noqa: E402


# ---------------------------------------------------------------------------
# Rate limit pure logic
# ---------------------------------------------------------------------------

def test_sms_rate_limit_first_call_allowed(monkeypatch):
    # Clear the module-level cache so prior tests don't leak.
    monkeypatch.setattr(dispatcher_mod, "_SMS_LAST_SENT", {})
    assert _sms_rate_limited("t1", "+97688111111") is False


def test_sms_rate_limit_second_call_within_window_blocked(monkeypatch):
    monkeypatch.setattr(dispatcher_mod, "_SMS_LAST_SENT", {})
    assert _sms_rate_limited("t1", "+97688111111") is False
    assert _sms_rate_limited("t1", "+97688111111") is True


def test_sms_rate_limit_different_phone_independent(monkeypatch):
    monkeypatch.setattr(dispatcher_mod, "_SMS_LAST_SENT", {})
    assert _sms_rate_limited("t1", "+97688111111") is False
    assert _sms_rate_limited("t1", "+97688222222") is False


def test_sms_rate_limit_different_tenant_independent(monkeypatch):
    monkeypatch.setattr(dispatcher_mod, "_SMS_LAST_SENT", {})
    assert _sms_rate_limited("t1", "+97688111111") is False
    assert _sms_rate_limited("t2", "+97688111111") is False


# ---------------------------------------------------------------------------
# Dispatcher integration
# ---------------------------------------------------------------------------

class _StubEscalationRepo:
    def __init__(self):
        self.deliveries: list[dict] = []
        self.failures: list[dict] = []

    async def log_delivery(self, *, alert_id, channel, recipient=None, delivered_at=None):
        self.deliveries.append(
            {"alert_id": alert_id, "channel": channel, "recipient": recipient}
        )
        return len(self.deliveries)

    async def log_failure(self, *, alert_id, channel, recipient=None, error):
        self.failures.append(
            {"alert_id": alert_id, "channel": channel, "recipient": recipient, "error": error}
        )
        return len(self.failures)


@pytest.fixture
def dispatcher_fixtures(monkeypatch):
    """Stub out AsyncSessionLocal + every repository the dispatcher
    touches so the test hits only the dispatch logic."""
    monkeypatch.setattr(dispatcher_mod, "_SMS_LAST_SENT", {})

    class _CM:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(dispatcher_mod, "AsyncSessionLocal", _CM)

    store_row = {
        "id": 1,
        "name": "Test Store",
        "telegram_chat_id": None,
        "settings": {
            "notification_channels": {
                "email": {"addresses": ["owner@test.mn"]},
                "sms": {"numbers": ["+97688111111"]},
                "telegram": {"chat_ids": []},
            },
        },
    }

    class _StubStoreRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _store_id):
            return store_row

    class _StubTgSubRepo:
        def __init__(self, _db):
            pass

        async def list_for_store(self, _store_id):
            return [{"chat_id": "chat-1", "role": "owner"}]

    class _StubPushRepo:
        def __init__(self, _db):
            pass

        async def list_for_store(self, _store_id):
            return [{"token": "device-abc-1234567890", "platform": "ios"}]

    repo_spy = _StubEscalationRepo()

    monkeypatch.setattr(dispatcher_mod, "StoreRepository", _StubStoreRepo)
    monkeypatch.setattr(dispatcher_mod, "TelegramSubscriberRepository", _StubTgSubRepo)
    monkeypatch.setattr(dispatcher_mod, "PushTokenRepository", _StubPushRepo)
    monkeypatch.setattr(
        dispatcher_mod, "AlertEscalationRepository", lambda _db: repo_spy
    )

    # Stub the live telegram_notifier so the test doesn't hit the network.
    fake_tg = AsyncMock()
    fake_tg.is_configured = True
    fake_tg.send_alert = AsyncMock(return_value=None)
    monkeypatch.setattr(dispatcher_mod, "telegram_notifier", fake_tg)

    return {
        "escalation_repo": repo_spy,
        "tg": fake_tg,
        "email": RecordingEmailSender(),
        "sms": RecordingSmsSender(),
        "fcm": RecordingFcmSender(),
    }


@pytest.mark.asyncio
async def test_yellow_dispatches_telegram_and_email_only(dispatcher_fixtures):
    fx = dispatcher_fixtures
    await dispatch_alert(
        AlertContext(
            alert_id=101, store_id=1, camera_id=5,
            severity="yellow", reason="R", image_path=None, score=45,
            tenant_id="tenant-a",
        ),
        email_sender=fx["email"], sms_sender=fx["sms"], fcm_sender=fx["fcm"],
    )
    channels = {d["channel"] for d in fx["escalation_repo"].deliveries}
    assert channels == {"telegram", "email"}
    assert len(fx["email"].sent) == 1
    assert fx["fcm"].sent == []
    assert fx["sms"].sent == []


@pytest.mark.asyncio
async def test_orange_adds_fcm(dispatcher_fixtures):
    fx = dispatcher_fixtures
    await dispatch_alert(
        AlertContext(
            alert_id=102, store_id=1, camera_id=5,
            severity="orange", reason="R", image_path=None, score=72,
            tenant_id="tenant-a",
        ),
        email_sender=fx["email"], sms_sender=fx["sms"], fcm_sender=fx["fcm"],
    )
    channels = {d["channel"] for d in fx["escalation_repo"].deliveries}
    assert channels == {"telegram", "email", "fcm"}
    assert len(fx["fcm"].sent) == 1
    assert fx["sms"].sent == []


@pytest.mark.asyncio
async def test_red_adds_sms(dispatcher_fixtures):
    fx = dispatcher_fixtures
    await dispatch_alert(
        AlertContext(
            alert_id=103, store_id=1, camera_id=5,
            severity="red", reason="R", image_path=None, score=95,
            tenant_id="tenant-a",
        ),
        email_sender=fx["email"], sms_sender=fx["sms"], fcm_sender=fx["fcm"],
    )
    channels = {d["channel"] for d in fx["escalation_repo"].deliveries}
    assert channels == {"telegram", "email", "fcm", "sms"}
    assert len(fx["sms"].sent) == 1


@pytest.mark.asyncio
async def test_red_sms_rate_limited_second_alert_same_tenant(dispatcher_fixtures):
    fx = dispatcher_fixtures
    await dispatch_alert(
        AlertContext(
            alert_id=104, store_id=1, camera_id=5,
            severity="red", reason="R", image_path=None, score=95,
            tenant_id="tenant-a",
        ),
        email_sender=fx["email"], sms_sender=fx["sms"], fcm_sender=fx["fcm"],
    )
    await dispatch_alert(
        AlertContext(
            alert_id=105, store_id=1, camera_id=5,
            severity="red", reason="R", image_path=None, score=95,
            tenant_id="tenant-a",
        ),
        email_sender=fx["email"], sms_sender=fx["sms"], fcm_sender=fx["fcm"],
    )
    # Only the first alert actually hits Twilio.
    assert len(fx["sms"].sent) == 1
    # The second alert is recorded as a failure row with rate_limited.
    rl_rows = [f for f in fx["escalation_repo"].failures if f["channel"] == "sms"]
    assert len(rl_rows) == 1
    assert "rate_limited" in rl_rows[0]["error"]


@pytest.mark.asyncio
async def test_green_severity_short_circuits(dispatcher_fixtures):
    fx = dispatcher_fixtures
    await dispatch_alert(
        AlertContext(
            alert_id=106, store_id=1, camera_id=5,
            severity="green", reason="R", image_path=None, score=10,
            tenant_id="tenant-a",
        ),
        email_sender=fx["email"], sms_sender=fx["sms"], fcm_sender=fx["fcm"],
    )
    assert fx["escalation_repo"].deliveries == []
    assert fx["email"].sent == []
    assert fx["sms"].sent == []


@pytest.mark.asyncio
async def test_email_failure_does_not_block_other_channels(dispatcher_fixtures):
    fx = dispatcher_fixtures

    class _FailingEmail:
        sent: list = []

        async def send(self, _msg):
            raise RuntimeError("smtp dropped")

    await dispatch_alert(
        AlertContext(
            alert_id=107, store_id=1, camera_id=5,
            severity="red", reason="R", image_path=None, score=95,
            tenant_id="tenant-b",  # fresh tenant so SMS isn't rate-limited
        ),
        email_sender=_FailingEmail(), sms_sender=fx["sms"], fcm_sender=fx["fcm"],
    )
    # Email recorded as failure, but telegram + fcm + sms all went out.
    channels_delivered = {d["channel"] for d in fx["escalation_repo"].deliveries}
    assert channels_delivered == {"telegram", "fcm", "sms"}
    channels_failed = {f["channel"] for f in fx["escalation_repo"].failures}
    assert "email" in channels_failed

"""Tests for T2-01 — signup orchestration."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from shoplift_detector.app.services.email_sender import RecordingEmailSender
from shoplift_detector.app.services.signup_service import (
    EmailAlreadyRegistered,
    signup_tenant,
)
from shoplift_detector.app.services.sms_sender import (
    RecordingSmsSender,
    SmsUnavailableError,
)


class _FakeTenantRepo:
    def __init__(self, *, raise_on_create=False):
        self._raise = raise_on_create
        self.created: dict | None = None

    async def create_pending(self, **kwargs):
        if self._raise:
            raise IntegrityError("UNIQUE", None, None)  # type: ignore[arg-type]
        self.created = kwargs
        row = {
            "tenant_id": uuid4(),
            "onboarding_step": "pending_email",
            **kwargs,
        }
        return row


class _FakeOtpRepo:
    def __init__(self):
        self.created: list[dict] = []

    async def create(self, **kwargs):
        row = {
            "id": uuid4(),
            "attempts": 0,
            "used_at": None,
            **kwargs,
        }
        self.created.append(row)
        return row


class _RaisingSms:
    def __init__(self, exc):
        self._exc = exc

    async def send(self, message):
        raise self._exc


@pytest.fixture(autouse=True)
def _patch_repos(monkeypatch):
    """All tests in this module share the same repo doubles. We patch
    the symbols on the signup_service module so production code paths
    don't need to change for tests."""
    import shoplift_detector.app.services.signup_service as svc

    tenant_repo = _FakeTenantRepo()
    otp_repo = _FakeOtpRepo()

    monkeypatch.setattr(svc, "TenantRepository", lambda db: tenant_repo)
    monkeypatch.setattr(svc, "OtpRepository", lambda db: otp_repo)
    # Expose the stubs so tests can assert against them.
    svc._test_tenant_repo = tenant_repo  # type: ignore[attr-defined]
    svc._test_otp_repo = otp_repo  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_signup_creates_tenant_and_dispatches_email_otp():
    import shoplift_detector.app.services.signup_service as svc

    email_sender = RecordingEmailSender()
    sms_sender = RecordingSmsSender()
    result = await signup_tenant(
        db=None,  # repos are stubbed via monkeypatch
        email="demo@sentry.mn",
        phone="+97688123456",
        store_name="Номин",
        email_sender=email_sender,
        sms_sender=sms_sender,
    )

    tenant_repo = svc._test_tenant_repo  # type: ignore[attr-defined]
    otp_repo = svc._test_otp_repo  # type: ignore[attr-defined]

    assert tenant_repo.created is not None
    assert tenant_repo.created["email"] == "demo@sentry.mn"
    assert tenant_repo.created["phone"] == "+97688123456"
    # resource_quota is starter defaults (trial tier).
    assert tenant_repo.created["resource_quota"]["max_cameras"] == 5

    # Two OTP rows: one email, one SMS.
    channels = sorted(row["channel"] for row in otp_repo.created)
    assert channels == ["email", "sms"]
    # Hashes must never match the raw code leaked to the senders.
    email_message = email_sender.sent[0]
    assert any(
        row["code_hash"] not in email_message.text_body
        for row in otp_repo.created
    )

    # Response envelope lists both delivered channels.
    assert sorted(result.otp_sent_to) == ["email", "sms"]
    assert result.onboarding_step == "pending_email"


@pytest.mark.asyncio
async def test_signup_without_phone_only_sends_email():
    email_sender = RecordingEmailSender()
    sms_sender = RecordingSmsSender()
    result = await signup_tenant(
        db=None,
        email="demo@sentry.mn",
        phone=None,
        store_name="Номин",
        email_sender=email_sender,
        sms_sender=sms_sender,
    )
    assert len(email_sender.sent) == 1
    assert sms_sender.sent == []
    assert result.otp_sent_to == ["email"]


@pytest.mark.asyncio
async def test_signup_falls_back_to_email_when_sms_provider_unavailable():
    """T2-03 fallback contract — SMS outage must not kill signup."""
    email_sender = RecordingEmailSender()
    sms = _RaisingSms(SmsUnavailableError("twilio 500"))
    result = await signup_tenant(
        db=None,
        email="demo@sentry.mn",
        phone="+97688123456",
        store_name="Номин",
        email_sender=email_sender,
        sms_sender=sms,
    )
    assert result.otp_sent_to == ["email"]
    assert len(email_sender.sent) == 1


@pytest.mark.asyncio
async def test_signup_swallows_unexpected_sms_errors_and_continues():
    email_sender = RecordingEmailSender()
    sms = _RaisingSms(RuntimeError("generic boom"))
    result = await signup_tenant(
        db=None,
        email="demo@sentry.mn",
        phone="+97688123456",
        store_name="Номин",
        email_sender=email_sender,
        sms_sender=sms,
    )
    assert result.otp_sent_to == ["email"]


@pytest.mark.asyncio
async def test_signup_raises_email_already_registered_on_conflict(monkeypatch):
    import shoplift_detector.app.services.signup_service as svc

    monkeypatch.setattr(
        svc, "TenantRepository",
        lambda db: _FakeTenantRepo(raise_on_create=True),
    )
    monkeypatch.setattr(svc, "OtpRepository", lambda db: _FakeOtpRepo())

    email_sender = RecordingEmailSender()
    with pytest.raises(EmailAlreadyRegistered):
        await signup_tenant(
            db=None,
            email="demo@sentry.mn",
            phone=None,
            store_name="Номин",
            email_sender=email_sender,
        )
    # Never sent the email — we bailed at tenant creation.
    assert email_sender.sent == []

"""Tests for T2-02 / T2-03 — email + SMS sender protocols + builders."""

import pytest

from shoplift_detector.app.services.email_sender import (
    OutgoingEmail,
    RecordingEmailSender,
    build_otp_email,
)
from shoplift_detector.app.services.sms_sender import (
    OutgoingSms,
    RecordingSmsSender,
    SmsUnavailableError,
    build_otp_sms,
)


# ---------------------------------------------------------------------------
# Recording senders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recording_email_sender_captures_payload():
    sender = RecordingEmailSender()
    message = OutgoingEmail(
        to="demo@sentry.mn",
        subject="Hi",
        text_body="Hello!",
    )
    provider_id = await sender.send(message)
    assert provider_id == "recorded-1"
    assert sender.sent == [message]


@pytest.mark.asyncio
async def test_recording_sms_sender_captures_payload():
    sender = RecordingSmsSender()
    msg = OutgoingSms(to="+97688123456", body="Hi")
    await sender.send(msg)
    assert sender.sent == [msg]


# ---------------------------------------------------------------------------
# OTP email builder
# ---------------------------------------------------------------------------

def test_build_otp_email_includes_code_and_store_name():
    msg = build_otp_email(
        to="demo@sentry.mn", code="123456", store_name="Номин"
    )
    assert msg.to == "demo@sentry.mn"
    assert "123456" in msg.text_body
    assert "Номин" in msg.text_body
    # Mongolian copy present.
    assert "баталгаажуулах код" in msg.text_body
    # HTML fallback included.
    assert msg.html_body is not None
    assert "123456" in msg.html_body


def test_build_otp_email_skips_personalization_when_store_missing():
    msg = build_otp_email(to="demo@sentry.mn", code="123456", store_name=None)
    assert "Сайн уу!" in msg.text_body
    assert "123456" in msg.text_body


def test_otp_email_from_address_defaults_to_sentry_domain():
    msg = build_otp_email(to="a@b", code="111111", store_name=None)
    assert "sentry.mn" in msg.from_addr


# ---------------------------------------------------------------------------
# OTP SMS builder
# ---------------------------------------------------------------------------

def test_build_otp_sms_has_mongolian_body_with_code():
    msg = build_otp_sms(code="123456")
    assert "123456" in msg.body
    assert "Sentry" in msg.body
    # Short enough for a single SMS segment (~160 chars).
    assert len(msg.body) <= 160


def test_sms_unavailable_error_is_a_runtime_error():
    # Important so the caller can `except SmsUnavailableError`
    # specifically without catching every RuntimeError in the stack.
    assert issubclass(SmsUnavailableError, RuntimeError)

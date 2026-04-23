"""Signup orchestration — tenant row + OTP + channel dispatch (T2-01..T2-04).

Kept as a plain coroutine so handlers stay thin and the same flow
can be driven from tests / admin tools without going through HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.quota import PLAN_QUOTA_DEFAULTS
from app.db.repository.tenants import TenantRepository
from app.services.api_key_service import generate_api_key
from app.services.email_sender import (
    EmailSender,
    build_otp_email,
)
from app.services.otp_service import OtpRepository, issue_otp
from app.services.sms_sender import (
    SmsSender,
    SmsUnavailableError,
    build_otp_sms,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignupResult:
    tenant_id: UUID
    email: str
    phone: str | None
    otp_sent_to: list[str]   # ["email"] or ["email", "sms"]
    onboarding_step: str


class EmailAlreadyRegistered(ValueError):
    """Raised when POST /signup hits a UNIQUE violation on email."""


async def signup_tenant(
    db: AsyncSession,
    *,
    email: str,
    phone: str | None,
    store_name: str,
    email_sender: EmailSender,
    sms_sender: SmsSender | None = None,
) -> SignupResult:
    """Create a pending tenant, issue an email OTP, optionally issue
    an SMS OTP, and return the correlation payload the handler
    surfaces to the client.

    Email is the ground truth; SMS is best-effort and falls through
    silently on provider outage (T2-03 fallback contract).
    """
    tenant_repo = TenantRepository(db)
    otp_repo = OtpRepository(db)

    # Every tenant gets an API key at creation time. Raw token never
    # surfaces through signup — rotation is the only way to retrieve
    # a plaintext key, by design.
    issued_key = generate_api_key()

    try:
        tenant = await tenant_repo.create_pending(
            email=email,
            phone=phone,
            legal_name=store_name,
            display_name=store_name,
            api_key_hash=issued_key.hashed,
            resource_quota=dict(PLAN_QUOTA_DEFAULTS["trial"]),
        )
    except IntegrityError as exc:
        raise EmailAlreadyRegistered(email) from exc

    tenant_id = tenant["tenant_id"]

    # Email OTP — the primary channel. Must succeed or the caller
    # can't complete signup at all.
    email_otp = await issue_otp(
        otp_repo,
        tenant_id=tenant_id,
        channel="email",
        destination=email,
    )
    await email_sender.send(
        build_otp_email(
            to=email, code=email_otp.raw_code, store_name=store_name
        )
    )
    delivered = ["email"]

    # SMS — best effort. On provider outage, drop silently; on any
    # other error, log + continue. The email path is enough for T2
    # acceptance criteria.
    if sms_sender is not None and phone:
        try:
            sms_otp = await issue_otp(
                otp_repo,
                tenant_id=tenant_id,
                channel="sms",
                destination=phone,
            )
            message = build_otp_sms(code=sms_otp.raw_code)
            message.to = phone
            await sms_sender.send(message)
            delivered.append("sms")
        except SmsUnavailableError as exc:
            logger.warning(
                "sms_otp_fallback_to_email",
                extra={"tenant_id": str(tenant_id), "reason": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "sms_otp_unexpected_error",
                extra={"tenant_id": str(tenant_id), "error": str(exc)},
            )

    return SignupResult(
        tenant_id=tenant_id,
        email=email,
        phone=phone,
        otp_sent_to=delivered,
        onboarding_step=tenant["onboarding_step"],
    )

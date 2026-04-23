"""Signup / OTP / plan-picker endpoints (T2-01, T2-02, T2-04, T2-06).

Mounted under `/api/v1/auth` (signup + verify) and `/api/v1/onboarding`
(plan picker). All endpoints are unauthenticated — the flow lives
between "no tenant yet" and "tenant active" states, so the normal
`get_current_tenant` dep isn't applicable.
"""

from __future__ import annotations

from typing import Annotated, Any

from app.core.config import settings
from app.core.phone_format import (
    InvalidMongolianPhone,
    normalize_phone,
)
from app.db.repository.tenants import TenantRepository
from app.db.session import DB
from app.services.email_sender import (
    RecordingEmailSender,
    ResendEmailSender,
)
from app.services.otp_service import (
    OtpCodeMismatch,
    OtpExhausted,
    OtpExpired,
    OtpNotFound,
    OtpRepository,
    verify_otp,
)
from app.services.plan_recommender import PLAN_FEATURES, build_picker
from app.services.signup_service import (
    EmailAlreadyRegistered,
    signup_tenant,
)
from app.services.trial_service import (
    TrialActivationError,
    activate_trial,
)
from app.services.sms_sender import (
    RecordingSmsSender,
    TwilioSmsSender,
)
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator

auth_signup_router = APIRouter()
onboarding_router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    store_name: str = Field(min_length=1, max_length=200)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        try:
            return normalize_phone(value)
        except InvalidMongolianPhone as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("store_name")
    @classmethod
    def _trim_store_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("store_name must not be blank")
        return stripped


class SignupResponse(BaseModel):
    tenant_id: str
    email: str
    phone: str | None
    otp_sent_to: list[str]
    onboarding_step: str
    message: str = (
        "Имэйл рүү тань баталгаажуулах код илгээлээ. "
        "15 минутын дотор оруулна уу."
    )


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class VerifyOtpResponse(BaseModel):
    tenant_id: str
    onboarding_step: str
    email_verified: bool


# ---------------------------------------------------------------------------
# Dependency factories
# ---------------------------------------------------------------------------

def _build_email_sender():
    if settings.RESEND_API_KEY:
        return ResendEmailSender(api_key=settings.RESEND_API_KEY)
    return RecordingEmailSender()


def _build_sms_sender():
    if (
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_FROM_NUMBER
    ):
        return TwilioSmsSender(
            account_sid=settings.TWILIO_ACCOUNT_SID,
            auth_token=settings.TWILIO_AUTH_TOKEN,
            from_number=settings.TWILIO_FROM_NUMBER,
        )
    return RecordingSmsSender()


# ---------------------------------------------------------------------------
# POST /api/v1/auth/signup  (T2-01)
# ---------------------------------------------------------------------------

@auth_signup_router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupResponse,
    summary="Create a pending tenant + issue email (and optional SMS) OTP",
)
async def signup(body: SignupRequest, db: DB) -> SignupResponse:
    email_sender = _build_email_sender()
    sms_sender = _build_sms_sender()

    try:
        result = await signup_tenant(
            db,
            email=body.email,
            phone=body.phone,
            store_name=body.store_name,
            email_sender=email_sender,
            sms_sender=sms_sender,
        )
    except EmailAlreadyRegistered:
        # Returning 409 is fine here — email uniqueness isn't a
        # secret. The attacker can enumerate emails via the landing
        # page reCAPTCHA surface anyway.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "email_already_registered",
                "message_mn": (
                    "Энэ имэйл өмнө нь бүртгэгдсэн. Нэвтрэх эсвэл "
                    "нууц үгээ сэргээнэ үү."
                ),
            },
        )
    return SignupResponse(
        tenant_id=str(result.tenant_id),
        email=result.email,
        phone=result.phone,
        otp_sent_to=result.otp_sent_to,
        onboarding_step=result.onboarding_step,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/verify-otp  (T2-04)
# ---------------------------------------------------------------------------

@auth_signup_router.post(
    "/verify-otp",
    response_model=VerifyOtpResponse,
    summary="Verify the email OTP and advance onboarding step",
)
async def verify_email_otp(body: VerifyOtpRequest, db: DB) -> VerifyOtpResponse:
    tenant_repo = TenantRepository(db)
    otp_repo = OtpRepository(db)

    tenant = await tenant_repo.get_by_email(body.email)
    if tenant is None:
        # Uniform 400 for every "bad input" path so a caller can't
        # enumerate registered emails via a different status code.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_verification"},
        )

    try:
        await verify_otp(
            otp_repo,
            tenant_id=tenant["tenant_id"],
            channel="email",
            submitted_code=body.code,
        )
    except (OtpNotFound, OtpCodeMismatch, OtpExpired, OtpExhausted):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_verification"},
        )

    await tenant_repo.mark_email_verified(tenant["tenant_id"])

    refreshed = await tenant_repo.get_by_email(body.email) or tenant
    return VerifyOtpResponse(
        tenant_id=str(refreshed["tenant_id"]),
        onboarding_step=refreshed.get("onboarding_step", "pending_plan"),
        email_verified=refreshed.get("email_verified_at") is not None,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/onboarding/activate-trial  (T2-07)
# ---------------------------------------------------------------------------

class ActivateTrialRequest(BaseModel):
    email: EmailStr


class ActivateTrialResponse(BaseModel):
    tenant_id: str
    api_key: str
    trial_ends_at: str
    plan: str
    onboarding_step: str
    resource_quota: dict
    message: str = (
        "14 хоногийн trial идэвхжсэн. API түлхүүрийг одоо хадгалаарай — "
        "дахин харуулахгүй."
    )


@onboarding_router.post(
    "/activate-trial",
    response_model=ActivateTrialResponse,
    summary="Activate a 14-day trial (skip payment, generate API key)",
)
async def activate_trial_endpoint(
    body: ActivateTrialRequest, db: DB
) -> ActivateTrialResponse:
    try:
        result = await activate_trial(db, email=body.email)
    except TrialActivationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "trial_activation_failed",
                "reason": str(exc),
            },
        )
    return ActivateTrialResponse(
        tenant_id=str(result.tenant_id),
        api_key=result.raw_api_key,
        trial_ends_at=result.trial_ends_at.isoformat(),
        plan=result.plan,
        onboarding_step=result.onboarding_step,
        resource_quota=result.resource_quota,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/onboarding/plan-picker  (T2-06)
# ---------------------------------------------------------------------------

@onboarding_router.get(
    "/plan-picker",
    summary="Plan picker cards + recommendation for the signup wizard",
)
async def plan_picker(
    camera_count: Annotated[int, Query(ge=1, le=500)] = 5,
    store_count: Annotated[int, Query(ge=1, le=100)] = 1,
    location: Annotated[str, Query()] = "ub",
    annual_prepay: Annotated[bool, Query()] = False,
    self_setup: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    picker = build_picker(
        camera_count=camera_count,
        store_count=store_count,
        location=location,
        annual_prepay=annual_prepay,
        self_setup=self_setup,
    )
    return {
        "camera_count": picker.camera_count,
        "store_count": picker.store_count,
        "location": picker.location,
        "annual_prepay": picker.annual_prepay,
        "recommended_plan": picker.recommended_plan,
        "cards": [
            {
                "plan": c.plan,
                "monthly_total": c.monthly_total,
                "annual_monthly": c.annual_monthly,
                "first_month_total": c.first_month_total,
                "features": c.features,
                "recommended": c.recommended,
            }
            for c in picker.cards
        ],
        "feature_catalog": PLAN_FEATURES,
    }

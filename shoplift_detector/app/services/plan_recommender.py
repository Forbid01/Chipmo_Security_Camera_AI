"""Plan recommendation for the signup wizard (T2-06).

The /plan picker shows three tier cards. The "⭐ Recommended" badge
is driven by camera count + store count:

    1–5 cams                     → Starter
    6–50 cams or 2–10 stores    → Pro
    51+ cams or 10+ stores      → Enterprise

Annual prepay toggles a 10% discount on the monthly number. The
existing `pricing_service.calculate_quote` already produces the
dollar math; this module adds the "which plan" layer + annual
discount + per-plan feature list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.pricing_service import calculate_quote

# 10% off when the customer prepays annually — matches 03_Pricing §9.
ANNUAL_DISCOUNT_PCT = 0.10

# Bucket ranges for the recommendation — inclusive lower, exclusive upper.
PLAN_CAMERA_TIERS: dict[str, tuple[int, int | None]] = {
    "starter": (1, 6),      # 1-5
    "pro": (6, 51),         # 6-50
    "enterprise": (51, None),
}

# Which feature bullets render on each card in the picker. Consumed
# verbatim by the React page in T2-05.
PLAN_FEATURES: dict[str, list[str]] = {
    "starter": [
        "5 хүртэл камер",
        "1 салбар",
        "Telegram + Web мэдэгдэл",
        "7-хоногийн clip хадгалалт",
        "Имэйл тусламж",
    ],
    "pro": [
        "6-50 камер",
        "10 хүртэл салбар",
        "Бүх мэдэгдлийн сувгууд (Telegram + SMS + Push + Email)",
        "30-хоногийн clip хадгалалт",
        "Cross-camera Re-ID",
        "Долоо хоногийн тайлан",
    ],
    "enterprise": [
        "51+ камер",
        "10+ салбар",
        "90-хоногийн clip хадгалалт",
        "Dedicated GPU",
        "24/7 утсан дэмжлэг + SLA",
        "SSO / SAML + DPA",
    ],
}


Recommendation = Literal["starter", "pro", "enterprise"]


@dataclass(frozen=True)
class PlanCard:
    """Single plan tier rendered on the /plan picker."""

    plan: str
    monthly_total: int
    annual_monthly: int
    first_month_total: int
    features: list[str]
    recommended: bool


@dataclass(frozen=True)
class PlanPickerResult:
    camera_count: int
    store_count: int
    location: str
    annual_prepay: bool
    recommended_plan: str
    cards: list[PlanCard]


def recommend_plan(
    *, camera_count: int, store_count: int = 1
) -> Recommendation:
    """Pick the best-fit tier for the customer's stated usage.

    Store count upshifts the recommendation — someone with 20 stores
    and 3 cameras each still belongs in Pro tier for the multi-store
    features, not Starter.
    """
    if camera_count < 1 or store_count < 1:
        raise ValueError("camera_count and store_count must be >= 1")

    if camera_count >= 51 or store_count > 10:
        return "enterprise"
    if camera_count >= 6 or store_count >= 2:
        return "pro"
    return "starter"


def _apply_annual_discount(monthly_total: int, annual_prepay: bool) -> int:
    if not annual_prepay:
        return monthly_total
    # Round down to the nearest ₮ — customer-facing numbers are
    # always integers on invoices.
    return int(monthly_total * (1 - ANNUAL_DISCOUNT_PCT))


def _camera_count_for_tier(plan: str, requested: int) -> int:
    """Clamp the requested count into the tier's range so each card's
    math stays representative. A user typing 50 cameras shouldn't see
    the Starter card priced for 50 — it'd be wildly off.
    """
    low, high = PLAN_CAMERA_TIERS[plan]
    if high is None:
        return max(requested, low)
    top = high - 1
    return min(max(requested, low), top)


def build_picker(
    *,
    camera_count: int,
    store_count: int = 1,
    location: str = "ub",
    annual_prepay: bool = False,
    self_setup: bool = False,
) -> PlanPickerResult:
    """Produce the full payload the /plan React page renders.

    Each card shows the price for the tier's representative camera
    count so Starter and Pro are comparable side-by-side. The
    `recommended` flag lights up exactly one card.
    """
    if camera_count < 1 or store_count < 1:
        raise ValueError("camera_count and store_count must be >= 1")

    recommended = recommend_plan(
        camera_count=camera_count, store_count=store_count
    )

    cards: list[PlanCard] = []
    for plan in ("starter", "pro", "enterprise"):
        card_cameras = _camera_count_for_tier(plan, camera_count)
        quote = calculate_quote(
            camera_count=card_cameras,
            store_count=store_count,
            location=location,
            self_setup=self_setup,
        )
        monthly = quote["monthly"]["total"]
        first_month = quote["summary"]["first_month_total"]
        cards.append(
            PlanCard(
                plan=plan,
                monthly_total=monthly,
                annual_monthly=_apply_annual_discount(monthly, annual_prepay),
                first_month_total=first_month,
                features=list(PLAN_FEATURES[plan]),
                recommended=(plan == recommended),
            )
        )

    return PlanPickerResult(
        camera_count=camera_count,
        store_count=store_count,
        location=location,
        annual_prepay=annual_prepay,
        recommended_plan=recommended,
        cards=cards,
    )

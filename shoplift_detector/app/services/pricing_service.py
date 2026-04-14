"""
Pricing service for Chipmo Security Camera AI.

3 components:
1. SaaS subscription — monthly (platform fee + per-camera volume discount)
2. Setup fee — one-time, per camera (Chipmo tech vs self-setup)
3. Visit/dispatch fee — one-time, per store (UB vs remote vs self)
"""

PLATFORM_FEE = 29_000  # ₮ per store per month

# Monthly per-camera tiers: (max_cameras, rate)
CAMERA_TIERS = [
    (5, 20_000),
    (20, 17_000),
    (50, 14_000),
    (None, 11_000),  # 51+
]

# One-time setup fee tiers: (max_cameras, chipmo_rate, self_rate)
SETUP_TIERS = [
    (5, 30_000, 15_000),
    (20, 25_000, 12_000),
    (None, 20_000, 10_000),  # 21+
]

# Visit/dispatch fee
VISIT_FEE_FIRST_STORE_UB = 50_000
VISIT_FEE_EXTRA_STORE_UB = 30_000
VISIT_FEE_PER_STORE_REMOTE = 20_000


def get_camera_rate(camera_count: int) -> int:
    """Return per-camera monthly rate based on volume tier."""
    if camera_count < 1:
        raise ValueError("camera_count must be at least 1")

    for max_cameras, rate in CAMERA_TIERS:
        if max_cameras is None or camera_count <= max_cameras:
            return rate

    return CAMERA_TIERS[-1][1]


def get_setup_rate(camera_count: int, self_setup: bool = False) -> int:
    """Return one-time setup fee per camera."""
    if camera_count < 1:
        raise ValueError("camera_count must be at least 1")

    for max_cameras, chipmo_rate, self_rate in SETUP_TIERS:
        if max_cameras is None or camera_count <= max_cameras:
            return self_rate if self_setup else chipmo_rate

    return SETUP_TIERS[-1][2 if self_setup else 1]


def get_visit_fee(store_count: int, location: str = "ub") -> int:
    """Calculate visit/dispatch fee.

    Args:
        store_count: Number of stores/branches.
        location: "ub" (Ulaanbaatar), "remote" (countryside), or "self" (no visit).

    Returns:
        Total visit fee in ₮.
    """
    if store_count < 1:
        raise ValueError("store_count must be at least 1")
    if location not in ("ub", "remote", "self"):
        raise ValueError("location must be 'ub', 'remote', or 'self'")

    if location == "self":
        return 0
    if location == "remote":
        return store_count * VISIT_FEE_PER_STORE_REMOTE

    # UB: first store 50k, additional stores 30k each
    return VISIT_FEE_FIRST_STORE_UB + max(0, store_count - 1) * VISIT_FEE_EXTRA_STORE_UB


def calculate_quote(
    camera_count: int,
    store_count: int,
    location: str = "ub",
    self_setup: bool = False,
) -> dict:
    """Calculate full pricing quote.

    Returns dict with monthly, one-time, and total breakdowns.
    """
    if camera_count < 1:
        raise ValueError("camera_count must be at least 1")
    if store_count < 1:
        raise ValueError("store_count must be at least 1")

    cam_rate = get_camera_rate(camera_count)
    monthly = (store_count * PLATFORM_FEE) + (camera_count * cam_rate)
    setup_rate = get_setup_rate(camera_count, self_setup)
    setup_fee = camera_count * setup_rate
    visit_fee = get_visit_fee(store_count, location)
    one_time = setup_fee + visit_fee

    return {
        "monthly": {
            "platform_fee_per_store": PLATFORM_FEE,
            "store_count": store_count,
            "platform_total": store_count * PLATFORM_FEE,
            "camera_rate": cam_rate,
            "camera_count": camera_count,
            "camera_total": camera_count * cam_rate,
            "total": monthly,
        },
        "one_time": {
            "setup_rate": setup_rate,
            "setup_type": "self" if self_setup else "chipmo",
            "setup_fee": setup_fee,
            "visit_fee": visit_fee,
            "location": location,
            "total": one_time,
        },
        "summary": {
            "first_month_total": monthly + one_time,
            "monthly_total": monthly,
            "annual_total": monthly * 12 + one_time,
        },
    }

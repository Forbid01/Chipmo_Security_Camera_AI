"""
Pricing service for Chipmo Security Camera AI.

Per-camera pricing with volume discounts + platform fee per organization.
"""

PLATFORM_FEE = 29_000  # ₮ per organization per month

# Volume discount tiers: (max_cameras, rate_per_camera)
# Ordered ascending by max cameras. Last tier has no upper bound.
CAMERA_TIERS = [
    (5, 20_000),
    (20, 17_000),
    (50, 14_000),
    (None, 11_000),  # 51+
]


def get_camera_rate(camera_count: int) -> int:
    """Return per-camera monthly rate based on volume tier.

    Args:
        camera_count: Total number of cameras.

    Returns:
        Per-camera rate in ₮.

    Raises:
        ValueError: If camera_count < 1.
    """
    if camera_count < 1:
        raise ValueError("camera_count must be at least 1")

    for max_cameras, rate in CAMERA_TIERS:
        if max_cameras is None or camera_count <= max_cameras:
            return rate

    # Should never reach here, but just in case
    return CAMERA_TIERS[-1][1]


def calculate_monthly_bill(camera_count: int, org_count: int = 1) -> dict:
    """Calculate total monthly bill.

    Args:
        camera_count: Total number of cameras across all organizations.
        org_count: Number of organizations.

    Returns:
        Dict with breakdown: platform_fee, camera_rate, camera_count,
        camera_total, grand_total.
    """
    if org_count < 1:
        raise ValueError("org_count must be at least 1")
    if camera_count < 0:
        raise ValueError("camera_count must be non-negative")

    camera_rate = get_camera_rate(camera_count) if camera_count > 0 else 0
    platform_total = org_count * PLATFORM_FEE
    camera_total = camera_count * camera_rate

    return {
        "platform_fee_per_org": PLATFORM_FEE,
        "org_count": org_count,
        "platform_total": platform_total,
        "camera_rate": camera_rate,
        "camera_count": camera_count,
        "camera_total": camera_total,
        "grand_total": platform_total + camera_total,
    }

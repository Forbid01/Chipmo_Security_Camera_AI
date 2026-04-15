"""Public pricing quote endpoint."""

from typing import Literal

from app.schemas.pricing import QuoteResponse
from app.services.pricing_service import calculate_quote
from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/quote", response_model=QuoteResponse)
async def get_quote(
    camera_count: int = Query(..., ge=1, le=500, description="Total number of cameras"),
    store_count: int = Query(1, ge=1, le=100, description="Number of stores"),
    location: Literal["ub", "remote", "self"] = Query("ub", description="ub | remote | self"),
    self_setup: bool = Query(False, description="Self-setup discount"),
):
    """Public pricing calculator — no auth required."""
    return calculate_quote(
        camera_count=camera_count,
        store_count=store_count,
        location=location,
        self_setup=self_setup,
    )

"""Pricing request/response schemas."""

from typing import Literal
from pydantic import BaseModel, Field


class QuoteRequest(BaseModel):
    camera_count: int = Field(..., ge=1, le=500, description="Total number of cameras")
    store_count: int = Field(1, ge=1, le=100, description="Number of stores/branches")
    location: Literal["ub", "remote", "self"] = Field("ub", description="ub=Ulaanbaatar, remote=countryside, self=no visit")
    self_setup: bool = Field(False, description="True if customer does setup themselves")


class MonthlyBreakdown(BaseModel):
    platform_fee_per_store: int
    store_count: int
    platform_total: int
    camera_rate: int
    camera_count: int
    camera_total: int
    total: int


class OneTimeBreakdown(BaseModel):
    setup_rate: int
    setup_type: str
    setup_fee: int
    visit_fee: int
    location: str
    total: int


class SummaryBreakdown(BaseModel):
    first_month_total: int
    monthly_total: int
    annual_total: int


class QuoteResponse(BaseModel):
    monthly: MonthlyBreakdown
    one_time: OneTimeBreakdown
    summary: SummaryBreakdown

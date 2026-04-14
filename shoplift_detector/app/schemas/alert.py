from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AlertResponse(BaseModel):
    id: int
    person_id: int
    organization_id: Optional[int] = None
    store_id: Optional[int] = None
    camera_id: Optional[int] = None
    event_time: datetime
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    web_url: Optional[str] = None
    video_url: Optional[str] = None
    description: Optional[str] = None
    confidence_score: Optional[float] = None
    reviewed: bool = False
    feedback_status: str = "unreviewed"
    store_name: Optional[str] = None
    organization_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertList(BaseModel):
    items: List[AlertResponse]
    total: int


class AlertFeedbackCreate(BaseModel):
    alert_id: int
    feedback_type: str  # true_positive, false_positive
    notes: Optional[str] = None


class AlertFeedbackResponse(BaseModel):
    id: int
    alert_id: int
    store_id: Optional[int] = None
    feedback_type: str
    reviewer_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertStats(BaseModel):
    total_alerts: int
    true_positives: int
    false_positives: int
    unreviewed: int
    precision: Optional[float] = None

from datetime import datetime

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: int
    person_id: int
    organization_id: int | None = None
    store_id: int | None = None
    camera_id: int | None = None
    event_time: datetime
    image_path: str | None = None
    video_path: str | None = None
    web_url: str | None = None
    video_url: str | None = None
    description: str | None = None
    confidence_score: float | None = None
    reviewed: bool = False
    feedback_status: str = "unreviewed"
    store_name: str | None = None
    organization_name: str | None = None

    model_config = {"from_attributes": True}


class AlertList(BaseModel):
    items: list[AlertResponse]
    total: int


class AlertFeedbackCreate(BaseModel):
    alert_id: int
    feedback_type: str  # true_positive, false_positive
    notes: str | None = None


class AlertFeedbackResponse(BaseModel):
    id: int
    alert_id: int
    store_id: int | None = None
    feedback_type: str
    reviewer_id: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertStats(BaseModel):
    total_alerts: int
    true_positives: int
    false_positives: int
    unreviewed: int
    precision: float | None = None

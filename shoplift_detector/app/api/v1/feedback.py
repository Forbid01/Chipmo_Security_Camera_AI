from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin_or_above
from app.db.session import get_db
from app.db.repository.feedback_repo import FeedbackRepository
from app.schemas.alert import AlertFeedbackCreate, AlertFeedbackResponse, AlertStats
from app.schemas.common import APIResponse

router = APIRouter()


@router.post("", response_model=APIResponse)
async def submit_feedback(
    data: AlertFeedbackCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Alert-д feedback өгөх (true_positive / false_positive).
    AI model энэ feedback-ээс автоматаар суралцана.
    """
    if data.feedback_type not in ("true_positive", "false_positive"):
        raise HTTPException(status_code=400, detail="feedback_type: true_positive эсвэл false_positive")

    repo = FeedbackRepository(db)
    feedback_id = await repo.create_feedback(
        alert_id=data.alert_id,
        feedback_type=data.feedback_type,
        reviewer_id=user.get("user_id"),
        notes=data.notes,
    )
    if not feedback_id:
        raise HTTPException(status_code=400, detail="Feedback өгөх боломжгүй")

    return APIResponse(message="Feedback амжилттай бүртгэгдлээ", data={"feedback_id": feedback_id})


@router.get("/stats")
async def feedback_stats(
    store_id: int = None,
    admin: dict = Depends(require_admin_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Дэлгүүрийн AI нарийвчлалын статистик."""
    repo = FeedbackRepository(db)
    stats = await repo.get_stats(store_id=store_id)
    return stats


@router.get("/learning-status")
async def learning_status(
    store_id: int = None,
    admin: dict = Depends(require_admin_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Auto-learning системийн одоогийн төлөв."""
    repo = FeedbackRepository(db)
    return await repo.get_learning_status(store_id=store_id)

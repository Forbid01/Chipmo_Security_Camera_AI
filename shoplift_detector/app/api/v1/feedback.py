from app.core.security import AdminOrAbove, CurrentUser
from app.db.repository.feedback_repo import FeedbackRepository
from app.db.session import DB
from app.schemas.alert import AlertFeedbackCreate
from app.schemas.common import APIResponse
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("", response_model=APIResponse)
async def submit_feedback(data: AlertFeedbackCreate, user: CurrentUser, db: DB):
    """Alert-д feedback өгөх (true_positive / false_positive).
    AI model энэ feedback-ээс автоматаар суралцана.
    """
    if data.feedback_type not in ("true_positive", "false_positive"):
        raise HTTPException(
            status_code=400, detail="feedback_type: true_positive эсвэл false_positive"
        )

    repo = FeedbackRepository(db)
    feedback_id = await repo.create_feedback(
        alert_id=data.alert_id,
        feedback_type=data.feedback_type,
        reviewer_id=user.get("user_id"),
        notes=data.notes,
    )
    if not feedback_id:
        raise HTTPException(status_code=400, detail="Feedback өгөх боломжгүй")

    return APIResponse(
        message="Feedback амжилттай бүртгэгдлээ", data={"feedback_id": feedback_id}
    )


@router.get("/stats")
async def feedback_stats(admin: AdminOrAbove, db: DB, store_id: int | None = None):
    """Дэлгүүрийн AI нарийвчлалын статистик."""
    repo = FeedbackRepository(db)
    return await repo.get_stats(store_id=store_id)


@router.get("/learning-status")
async def learning_status(admin: AdminOrAbove, db: DB, store_id: int | None = None):
    """Auto-learning системийн одоогийн төлөв."""
    repo = FeedbackRepository(db)
    return await repo.get_learning_status(store_id=store_id)

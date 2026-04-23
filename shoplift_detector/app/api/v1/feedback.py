from typing import Annotated

from app.core.security import AdminOrAbove, CurrentUser
from app.core.tenancy import require_alert_access, require_store_access
from app.db.repository.feedback_repo import FeedbackRepository
from app.db.session import DB
from app.schemas.alert import AlertFeedbackCreate
from app.schemas.common import APIResponse
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


async def _require_alert_from_payload(
    data: AlertFeedbackCreate,
    user: CurrentUser,
    db: DB,
) -> dict:
    """Alert dependency for POST bodies. Delegates to require_alert_access
    with the body's alert_id so the same tenant check runs before we
    touch the repository. Closes H-H9 from T02-12.
    """
    return await require_alert_access(data.alert_id, user, db)


@router.post("", response_model=APIResponse)
async def submit_feedback(
    data: AlertFeedbackCreate,
    user: CurrentUser,
    db: DB,
    alert: Annotated[dict, Depends(_require_alert_from_payload)],
):
    """Alert-д feedback өгөх (true_positive / false_positive).
    AI model энэ feedback-ээс автоматаар суралцана.

    Tenant scoping: `_require_alert_from_payload` enforces that the
    alert belongs to the caller's organization (T02-21). Closes H-H9.
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


async def _resolve_store_scope(
    admin: AdminOrAbove,
    db: DB,
    store_id: int | None = None,
) -> int | None:
    """Pick the effective store_id filter for feedback aggregate queries.

    - super_admin: respects the query param (None = global aggregate)
    - admin: store_id must be supplied AND owned by the admin's org
             (otherwise 404 via require_store_access). Without store_id,
             returns an org-implied sentinel handled by the caller.
    Closes H-H10 / H-H11 from T02-12.
    """
    if admin.get("role") == "super_admin":
        return store_id

    if store_id is None:
        # Non-super admin calling the aggregate without a store filter
        # would receive a cross-org total. Force them to pick a store
        # they own.
        raise HTTPException(
            status_code=400,
            detail="store_id заавал оруулна уу (non-super admin)",
        )

    await require_store_access(store_id, admin, db)
    return store_id


@router.get("/stats")
async def feedback_stats(
    db: DB,
    effective_store_id: Annotated[int | None, Depends(_resolve_store_scope)],
):
    """Дэлгүүрийн AI нарийвчлалын статистик. Tenant-guarded."""
    repo = FeedbackRepository(db)
    return await repo.get_stats(store_id=effective_store_id)


@router.get("/learning-status")
async def learning_status(
    db: DB,
    effective_store_id: Annotated[int | None, Depends(_resolve_store_scope)],
):
    """Auto-learning системийн одоогийн төлөв. Tenant-guarded."""
    repo = FeedbackRepository(db)
    return await repo.get_learning_status(store_id=effective_store_id)

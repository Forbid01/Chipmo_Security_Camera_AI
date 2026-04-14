import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_super_admin
from app.core.config import ALERTS_DIR
from app.db.session import get_db
from app.db.repository.alerts import AlertRepository
from app.schemas.common import APIResponse

router = APIRouter()


@router.get("")
async def get_alerts(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    store_id: int = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = AlertRepository(db)
    org_id = user.get("org_id")

    if user.get("role") == "super_admin":
        alerts = await repo.get_latest_alerts(
            organization_id=None, store_id=store_id, limit=limit, offset=offset
        )
    else:
        alerts = await repo.get_latest_alerts(
            organization_id=org_id, store_id=store_id, limit=limit, offset=offset
        )

    base_url = str(request.base_url).rstrip("/")
    for alert in alerts:
        image_path = alert.get("image_path")
        if not image_path:
            alert["web_url"] = None
            alert["video_url"] = None
            continue

        file_name = os.path.basename(image_path)
        video_name = file_name.replace('.jpg', '.mp4')
        video_full_path = os.path.join(ALERTS_DIR, video_name)
        alert['web_url'] = f"{base_url}/static/{file_name}"
        alert['video_url'] = f"{base_url}/static/{video_name}" if os.path.exists(video_full_path) else None

    return {"status": "success", "data": alerts}


@router.get("/admin")
async def get_admin_alerts(
    organization_id: int = None,
    store_id: int = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = AlertRepository(db)
    return await repo.get_all_alerts_admin(organization_id, store_id, limit, offset)


@router.put("/{alert_id}/reviewed", response_model=APIResponse)
async def mark_reviewed(
    alert_id: int,
    admin: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = AlertRepository(db)
    success = await repo.mark_alert_reviewed(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert олдсонгүй")
    return APIResponse(message="Alert шалгагдсан гэж тэмдэглэгдлээ")


@router.delete("/{alert_id}", response_model=APIResponse)
async def delete_alert(
    alert_id: int,
    admin: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = AlertRepository(db)
    success = await repo.delete_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert олдсонгүй")
    return APIResponse(message="Alert устгагдлаа")

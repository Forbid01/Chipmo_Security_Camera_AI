from fastapi import APIRouter
from .auth import router as auth_router
from .admin import router as admin_router
from .alerts import router as alerts_router
from .cameras import router as cameras_router
from .stores import router as stores_router
from .video import router as video_router
from .feedback import router as feedback_router
from .my_cameras import router as my_cameras_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(cameras_router, prefix="/cameras", tags=["Cameras"])
api_router.include_router(stores_router, prefix="/stores", tags=["Stores"])
api_router.include_router(video_router, prefix="/video", tags=["Video Streaming"])
api_router.include_router(feedback_router, prefix="/feedback", tags=["AI Feedback & Learning"])
api_router.include_router(my_cameras_router, prefix="/my/cameras", tags=["My Cameras"])

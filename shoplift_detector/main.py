import os

# Must be set BEFORE ultralytics is imported anywhere — Railway has no
# writable ~/.config, so ultralytics otherwise spams warnings and falls back.
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp")

import asyncio  # noqa: E402
import random  # noqa: E402
import string  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from typing import Annotated  # noqa: E402

import cv2  # noqa: E402
import uvicorn  # noqa: E402

# Path setup (must run before any `app.*` imports so the project root resolves)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.api.v1 import api_router  # noqa: E402
from app.api.v1.admin import (  # noqa: E402
    create_organization,
    delete_organization,
    delete_user,
    get_organizations,
    get_stats,
    get_users,
    update_user_org,
    update_user_role,
)
from app.api.v1.alerts import delete_alert, get_admin_alerts, mark_reviewed  # noqa: E402
from app.api.v1.cameras import (  # noqa: E402
    create_camera,
    delete_camera,
    list_cameras,
    update_camera,
)
from app.core.config import ALERTS_DIR, settings  # noqa: E402
from app.core.logging import get_logger, setup_logging  # noqa: E402
from app.core.security import (  # noqa: E402
    CurrentUser,
    create_access_token,
    get_password_hash,
    set_auth_cookie,
    validate_password_strength,
    verify_password,
)
from app.db.models import Base  # noqa: E402
from app.db.repository.alerts import AlertRepository  # noqa: E402
from app.db.repository.users import UserRepository  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.schemas.auth import (  # noqa: E402
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyCodeRequest,
)
from app.schemas.auth import UserCreate as UserCreateSchema  # noqa: E402
from app.schemas.user import ContactForm  # noqa: E402
from app.services.ai_service import ai_inference  # noqa: E402
from app.services.alert_service import alert_worker  # noqa: E402
from app.services.camera_manager import camera_manager  # noqa: E402
from app.services.email_service import send_contact_email, send_otp_email  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.security import OAuth2PasswordRequestForm  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from slowapi import Limiter  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.util import get_remote_address  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

setup_logging()
logger = get_logger(__name__)


LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


# --- Security Headers Middleware ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # [STARTUP]
    logger.info("initializing_database")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created")

    await _load_cameras_from_db()

    from app.services.telegram_notifier import telegram_notifier
    telegram_notifier.configure(settings.TELEGRAM_TOKEN)

    logger.info("starting_background_services")
    threading.Thread(target=alert_worker, daemon=True, name="alert-worker").start()
    threading.Thread(target=ai_inference, daemon=True, name="ai-inference").start()
    threading.Thread(target=_auto_learning_loop, daemon=True, name="auto-learner").start()

    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
            logger.info("sentry_initialized")
        except ImportError:
            pass

    yield

    # [SHUTDOWN]
    logger.info("shutting_down")
    # Release VideoCapture handles and destroy any OpenCV windows so Railway
    # doesn't leave ghost ffmpeg workers around between redeploys.
    camera_manager.shutdown_all()


async def _load_cameras_from_db():
    """DB-ээс бүх идэвхтэй камеруудыг ачаалж, CameraManager-д бүртгэх."""
    from app.db.repository.camera_repo import CameraRepository

    try:
        async with AsyncSessionLocal() as db:
            repo = CameraRepository(db)
            cameras = await repo.get_active_cameras()

            for cam in cameras:
                camera_manager.register_camera(
                    camera_id=cam["id"],
                    store_id=cam.get("store_id", 0),
                    name=cam["name"],
                    url=cam["url"],
                    camera_type=cam.get("camera_type", "rtsp"),
                    is_ai_enabled=cam.get("is_ai_enabled", True),
                    alert_threshold=cam.get("alert_threshold", 80.0),
                    alert_cooldown=cam.get("alert_cooldown", 15),
                )

            logger.info("cameras_loaded", count=len(cameras))
    except Exception as e:
        logger.error("camera_load_error", error=str(e))

    # Single-source override (CAMERA_SOURCE) wins when set — lets a Railway
    # deploy point at an RTSP URL without touching the DB.
    if settings.CAMERA_SOURCE:
        cam_type = "usb" if settings.CAMERA_SOURCE.isdigit() else "rtsp"
        camera_manager.register_camera(
            camera_id=9000,
            store_id=0,
            name="Default",
            url=settings.CAMERA_SOURCE,
            camera_type=cam_type,
        )
        return

    # Default-camera bootstrap is opt-in. It's useful locally (Mac webcam,
    # phone IP cam) but dangerous in prod — Railway has no /dev/video0,
    # which previously caused an infinite RTSP reconnect loop.
    if not settings.ENABLE_DEFAULT_CAMERAS:
        return

    from app.core.config import DEFAULT_CAMERA_SOURCES
    default_id = 9000
    for cam_type, source in DEFAULT_CAMERA_SOURCES.items():
        if cam_type == "mac":
            idx = settings.MAC_CAMERA_INDEX
            if idx is None or idx < 0:
                continue
            if not os.path.exists(f"/dev/video{idx}"):
                logger.info(
                    "skipping_default_mac_camera",
                    reason="no_video_device",
                    index=idx,
                )
                continue
            source = idx
        if not source and source != 0:
            continue
        camera_manager.register_camera(
            camera_id=default_id,
            store_id=0,
            name=f"Default-{cam_type}",
            url=str(source),
            camera_type="usb" if cam_type == "mac" else "mjpeg",
        )
        default_id += 1


def _auto_learning_loop():
    """Background thread: тогтмол хугацаанд feedback-ээс суралцах."""
    import time

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            time.sleep(300)
            if settings.AI_AUTO_LEARN:
                loop.run_until_complete(_run_auto_learning())
        except Exception as e:
            logger.error("auto_learning_error", error=str(e))


async def _run_auto_learning():
    from app.services.auto_learner import auto_learner

    async with AsyncSessionLocal() as db:
        updated = await auto_learner.learn_from_feedback(db)
        if updated:
            logger.info("auto_learning_complete", stores_updated=len(updated))


# --- FastAPI App ---
app = FastAPI(
    title="Chipmo Security AI",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"status": "error", "message": "Хэт олон хүсэлт. Түр хүлээнэ үү."},
    )


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if settings.ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=ALERTS_DIR), name="static")

app.include_router(api_router)


# --- Legacy endpoints (backward compat with frontend) ---

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "cameras": {
            "total": camera_manager.get_camera_count(),
            "connected": camera_manager.get_connected_count(),
        },
        "database": "connected",
    }


@app.post("/token")
@limiter.limit("10/minute")
async def legacy_login(request: Request, response: Response, form_data: LoginForm):
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        user = await repo.get_by_identifier(form_data.username)

    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Нэвтрэх нэр эсвэл нууц үг буруу")

    token = create_access_token(data={
        "sub": user["username"],
        "role": user.get("role", "user"),
        "org_id": user.get("organization_id"),
        "user_id": user.get("id"),
    })
    set_auth_cookie(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user.get("full_name"),
            "role": user.get("role", "user"),
            "org_id": user.get("organization_id"),
            "org_name": user.get("organization_name"),
        },
    }


@app.get("/users/me")
async def legacy_users_me(current_user: CurrentUser):
    user = current_user
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        full_user = await repo.get_by_identifier(user["username"])

    if not full_user:
        raise HTTPException(status_code=404, detail="Хэрэглэгч олдсонгүй")
    return {
        "username": full_user["username"],
        "full_name": full_user.get("full_name"),
        "email": full_user.get("email"),
        "role": full_user.get("role", "user"),
        "org_id": full_user.get("organization_id"),
        "org_name": full_user.get("organization_name"),
    }


@app.get("/alerts")
async def legacy_alerts(request: Request, current_user: CurrentUser):
    user = current_user
    async with AsyncSessionLocal() as db:
        repo = AlertRepository(db)
        org_id = user.get("org_id")
        if user.get("role") == "super_admin":
            alerts = await repo.get_latest_alerts(organization_id=None, limit=20)
        else:
            alerts = await repo.get_latest_alerts(organization_id=org_id, limit=20)

    base_url = str(request.base_url).rstrip("/")
    for alert in alerts:
        image_path = alert.get("image_path")
        if not image_path:
            alert["web_url"] = None
            alert["video_url"] = None
            continue
        if image_path.startswith(("http://", "https://")):
            alert["web_url"] = image_path
            alert["video_url"] = None
            continue
        file_name = os.path.basename(image_path)
        video_name = file_name.replace(".jpg", ".mp4")
        video_full_path = os.path.join(ALERTS_DIR, video_name)
        alert["web_url"] = f"{base_url}/static/{file_name}"
        alert["video_url"] = (
            f"{base_url}/static/{video_name}" if os.path.exists(video_full_path) else None
        )

    return {"status": "success", "data": alerts}


async def _legacy_gen_frames(camera_type: str):
    import time as _time
    cam_map = {"mac": 9000, "phone": 9001, "axis": 9002}
    cam_id = cam_map.get(camera_type)
    interval = 1.0 / 15  # 15 FPS cap — same policy as /api/v1/video
    last_sent = 0.0
    last_frame_id = None
    while True:
        wait = interval - (_time.monotonic() - last_sent)
        if wait > 0:
            await asyncio.sleep(wait)
        frame = camera_manager.get_frame(cam_id) if cam_id else None
        if frame is None:
            await asyncio.sleep(0.1)
            continue
        fid = id(frame)
        if fid == last_frame_id:
            await asyncio.sleep(interval / 2)
            continue
        last_frame_id = fid
        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ret:
            last_sent = _time.monotonic()
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"


@app.get("/video_feed")
async def legacy_video_feed():
    return StreamingResponse(
        _legacy_gen_frames("mac"), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/video_feed/{camera_id}")
async def legacy_video_feed_by_id(camera_id: str):
    if camera_id not in ("mac", "phone", "axis"):
        raise HTTPException(status_code=404, detail="Камер олдсонгүй")
    return StreamingResponse(
        _legacy_gen_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/register")
async def legacy_register(user_data: UserCreateSchema):
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        existing = await repo.get_by_identifier(user_data.username)
        if existing:
            raise HTTPException(status_code=400, detail="Хэрэглэгчийн нэр бүртгэлтэй байна")
        existing_email = await repo.get_by_email(user_data.email)
        if existing_email:
            raise HTTPException(status_code=400, detail="Имэйл бүртгэлтэй байна")

        org_id = None
        if user_data.org_name:
            org_id = await repo.get_or_create_organization(user_data.org_name.strip())

        hashed_pwd = get_password_hash(user_data.password)
        user_id = await repo.create(
            username=user_data.username,
            email=user_data.email,
            phone_number=user_data.phone_number,
            hashed_password=hashed_pwd,
            full_name=user_data.full_name,
            organization_id=org_id,
        )
    return {"message": "Хэрэглэгч амжилттай бүртгэгдлээ", "user_id": user_id}


@app.post("/api/contact")
async def legacy_contact(form: ContactForm):
    try:
        await send_contact_email(
            name=form.name,
            email=form.email,
            subject=form.subject,
            message=form.message,
        )
        return {"status": "success", "message": "Email sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Legacy admin endpoints - forward to v1
app.add_api_route("/admin/organizations", get_organizations, methods=["GET"])
app.add_api_route("/admin/organizations", create_organization, methods=["POST"])
app.add_api_route(
    "/admin/organizations/{org_id}", delete_organization, methods=["DELETE"]
)
app.add_api_route("/admin/users", get_users, methods=["GET"])
app.add_api_route("/admin/users/{user_id}/role", update_user_role, methods=["PUT"])
app.add_api_route(
    "/admin/users/{user_id}/organization", update_user_org, methods=["PUT"]
)
app.add_api_route("/admin/users/{user_id}", delete_user, methods=["DELETE"])
app.add_api_route("/admin/stats", get_stats, methods=["GET"])

app.add_api_route("/admin/alerts", get_admin_alerts, methods=["GET"])
app.add_api_route("/admin/alerts/{alert_id}/reviewed", mark_reviewed, methods=["PUT"])
app.add_api_route("/admin/alerts/{alert_id}", delete_alert, methods=["DELETE"])

app.add_api_route("/admin/cameras", list_cameras, methods=["GET"])
app.add_api_route("/admin/cameras", create_camera, methods=["POST"])
app.add_api_route("/admin/cameras/{camera_id}", update_camera, methods=["PUT"])
app.add_api_route("/admin/cameras/{camera_id}", delete_camera, methods=["DELETE"])


@app.post("/forgot-password")
async def legacy_forgot_password(request: Request, data: ForgotPasswordRequest):
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        user = await repo.get_by_email(data.email)
        if not user:
            return {"message": "Хэрэв имэйл бүртгэлтэй бол сэргээх код илгээгдлээ"}
        otp_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        expiry = datetime.now(UTC) + timedelta(minutes=15)
        await repo.update_recovery_data(user["id"], otp_code, expiry)
        await send_otp_email(data.email, otp_code)
    return {"message": "Сэргээх код имэйл рүү илгээгдлээ"}


@app.post("/verify-code")
async def legacy_verify_code(request: Request, data: VerifyCodeRequest):
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        user = await repo.get_by_email(data.email)
        if not user:
            raise HTTPException(status_code=400, detail="Код буруу")
        if user.get("recovery_code") != data.code:
            raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")
        expiry = user.get("recovery_code_expires")
        if not expiry or expiry < datetime.now(UTC):
            raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")
    return {"message": "Код баталгаажлаа"}


@app.post("/reset-password")
async def legacy_reset_password(request: Request, data: ResetPasswordRequest):
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        user = await repo.get_by_email(data.email)
        if not user:
            raise HTTPException(status_code=400, detail="Алдаа гарлаа")
        if user.get("recovery_code") != data.code:
            raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")
        expiry = user.get("recovery_code_expires")
        if not expiry or expiry < datetime.now(UTC):
            raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")
        validate_password_strength(data.new_password)
        hashed_pwd = get_password_hash(data.new_password)
        await repo.update_password(user["id"], hashed_pwd)
        await repo.clear_recovery_data(user["id"])
    return {"message": "Нууц үг амжилттай шинэчлэгдлээ"}


# --- SPA Frontend ---
dist_path = os.path.join(BASE_DIR, "dist")
if os.path.exists(dist_path):
    assets_path = os.path.join(dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    def _serve_spa_path(request_path: str):
        if request_path:
            candidate = os.path.normpath(os.path.join(dist_path, request_path))
            if candidate.startswith(dist_path) and os.path.isfile(candidate):
                return FileResponse(candidate)

        index_file = os.path.join(dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return JSONResponse(status_code=500, content={"error": "Frontend build not found"})

    @app.get("/")
    async def serve_react_root():
        return _serve_spa_path("")

    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        api_prefixes = [
            "api", "auth", "admin", "video_feed", "static", "assets",
            "token", "health", "docs", "redoc", "openapi.json",
            "users", "alerts", "register", "forgot-password", "verify-code", "reset-password",
        ]
        if any(catchall.startswith(prefix) for prefix in api_prefixes):
            raise HTTPException(status_code=404)
        return _serve_spa_path(catchall)


# --- Run Server ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", settings.PORT))
    logger.info("starting_server", port=port, version=settings.APP_VERSION)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

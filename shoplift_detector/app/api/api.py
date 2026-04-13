import os
import logging
import cv2
import asyncio
import numpy as np
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

# Тохиргоо болон State-үүд
from app.core.config import ALERTS_DIR, ALLOWED_ORIGINS
import app.core.state as state
from app.db.repository.alerts import AlertRepository

# Аюулгүй байдал болон Router-үүд
from app.api.auth import router as auth_router
from app.services.auth_service import AuthService

from pydantic import EmailStr, BaseModel
from app.services.email_service import send_contact_email

logger = logging.getLogger(__name__)

# Rate limiter тохиргоо
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Chipmo Security AI Portal", docs_url="/docs", redoc_url="/redoc")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Хэт олон хүсэлт илгээлээ. Түр хүлээнэ үү."}
    )


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)

alert_repo = AlertRepository()

# Статик файлуудыг холбох (Зураг, Видео)
app.mount("/static", StaticFiles(directory=ALERTS_DIR), name="static")

# CORS Тохиргоо
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- AUTH ROUTER ИНТЕГРАЦИ ---
app.include_router(auth_router)


# --- HEALTH CHECK ---
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "cameras": {
            "mac": state.latest_mac_frame is not None,
            "phone": state.latest_phone_frame is not None,
            "axis": state.latest_axis_frame is not None,
        },
        "queues": {
            "ai_input": state.ai_input_queue.qsize(),
            "alert": state.alert_queue.qsize(),
        },
    }

# --- VIDEO STREAMING LOGIC ---

VALID_CAMERA_IDS = {"mac", "phone", "axis"}


def get_camera_frame(camera_id: str):
    return state.get_latest_frame(camera_id)

async def generate_frames():
    while True:
        try:
            frames_to_show = []
            if state.latest_mac_frame is not None:
                frames_to_show.append(state.latest_mac_frame.copy())
            if state.latest_phone_frame is not None:
                frames_to_show.append(state.latest_phone_frame.copy())

            if not frames_to_show:
                await asyncio.sleep(0.1)
                continue

            if len(frames_to_show) == 2:
                h1, w1 = frames_to_show[0].shape[:2]
                h2, w2 = frames_to_show[1].shape[:2]
                if h1 != h2:
                    new_w2 = int(w2 * (h1 / h2))
                    frames_to_show[1] = cv2.resize(frames_to_show[1], (new_w2, h1))
                combined_frame = np.hstack((frames_to_show[0], frames_to_show[1]))
            else:
                combined_frame = frames_to_show[0]

            ret, buffer = cv2.imencode('.jpg', combined_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ret:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            await asyncio.sleep(0.033)

        except Exception as e:
            logger.error(f"Streaming Error: {e}")
            await asyncio.sleep(0.1)


async def generate_camera_frames(camera_id: str):
    while True:
        try:
            frame = get_camera_frame(camera_id)
            if frame is None:
                await asyncio.sleep(0.1)
                continue

            ret, buffer = cv2.imencode(".jpg", frame.copy(), [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ret:
                await asyncio.sleep(0.03)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
            await asyncio.sleep(0.033)
        except Exception as exc:
            logger.error(f"{camera_id} stream error: {exc}")
            await asyncio.sleep(0.1)

# --- AUTH ENDPOINTS (REACT LOGIN-Д ЗОРИУЛСАН) ---

@app.post("/token")
@limiter.limit("10/minute")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    React Login.jsx-ээс ирэх хүсэлтийг хүлээн авч, 
    AuthService-ээр баталгаажуулан JWT токен болон User Role-ийг буцаана.
    """
    user = AuthService.authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нэвтрэх нэр эсвэл нууц үг буруу байна",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Payload-д хэрэглэгчийн мэдээллийг нууцлан хийнэ
    access_token = AuthService.create_access_token(
        data={
            "sub": user["username"],
            "role": user.get("role", "user"),
            "org_id": user.get("organization_id")
        }
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "role": user.get("role", "user"),
            "org_id": user.get("organization_id")
        }
    }

@app.get("/users/me")
async def read_users_me(current_user: dict = Depends(AuthService.get_current_user)):
    """Одоо нэвтэрсэн байгаа хэрэглэгчийн мэдээллийг буцаана"""
    return current_user

# --- CONTACT FORM ---

class ContactForm(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

@app.post("/api/contact")
async def contact_us(form: ContactForm):
    try:
        await send_contact_email(
            name=form.name,
            email=form.email,
            subject=form.subject,
            message=form.message
        )
        return {"status": "success", "message": "Email sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- VIDEO & ALERTS ---

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/video_feed/{camera_id}")
async def video_feed_by_camera(camera_id: str):
    if camera_id not in VALID_CAMERA_IDS:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй")

    return StreamingResponse(
        generate_camera_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

@app.get("/alerts")
async def get_alerts(request: Request, user: dict = Depends(AuthService.get_current_user)):
    try:
        org_id = user.get("org_id")
        if user.get("role") == "super_admin":
            alerts = alert_repo.get_latest_alerts(organization_id=None, limit=20)
        else:
            alerts = alert_repo.get_latest_alerts(organization_id=org_id, limit=20)
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
            if os.path.exists(video_full_path):
                alert['video_url'] = f"{base_url}/static/{video_name}"
            else:
                alert['video_url'] = None

        return {"status": "success", "data": alerts}
    except Exception as e:
        logger.error(f"Alerts endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Alert мэдээлэл уншихад алдаа гарлаа.")

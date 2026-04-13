import os
import cv2
import asyncio
import numpy as np
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

# Тохиргоо болон State-үүд
from app.core.config import ALERTS_DIR
import app.core.state as state
from app.db.repository.alerts import AlertRepository

# Аюулгүй байдал болон Router-үүд
# ТАЙЛБАР: Замууд нь чиний хавтасны бүтцээс хамаарч өөр байж магадгүй, шалгаарай!
from app.api.auth import router as auth_router
from app.services.auth_service import AuthService

from pydantic import EmailStr, BaseModel
from app.services.email_service import send_contact_email

app = FastAPI(title="Chipmo Security AI Portal")
alert_repo = AlertRepository()

# Статик файлуудыг холбох (Зураг, Видео)
app.mount("/static", StaticFiles(directory=ALERTS_DIR), name="static")

# CORS Тохиргоо (React-оос хандах боломжийг нээнэ)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- AUTH ROUTER ИНТЕГРАЦИ ---
# Энэ мөр нь /auth/register, /auth/login, /auth/admin/... бүх замыг идэвхжүүлнэ
app.include_router(auth_router)

# --- VIDEO STREAMING LOGIC ---

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
            print(f"Streaming Error: {e}")
            await asyncio.sleep(0.1)

# --- AUTH ENDPOINTS (REACT LOGIN-Д ЗОРИУЛСАН) ---

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
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

@app.get("/alerts")
async def get_alerts(request: Request, user: dict = Depends(AuthService.get_current_user)):
    try:
        # Хэрэв энгийн хэрэглэгч бол зөвхөн өөрийн байгууллагын алдааг харна гэх мэт 
        # логик энд нэмж болно (user['org_id'] ашиглаад)
        alerts = alert_repo.get_latest_alerts(limit=20)
        base_url = str(request.base_url).rstrip("/")

        for alert in alerts:
            file_name = os.path.basename(alert['image_path'])
            video_name = file_name.replace('.jpg', '.mp4')
            video_full_path = os.path.join(ALERTS_DIR, video_name)
            alert['web_url'] = f"{base_url}/static/{file_name}"
            if os.path.exists(video_full_path):
                alert['video_url'] = f"{base_url}/static/{video_name}"
            else:
                alert['video_url'] = None

        return {"status": "success", "data": alerts}
    except Exception as e:
        return {"status": "error", "message": str(e)}
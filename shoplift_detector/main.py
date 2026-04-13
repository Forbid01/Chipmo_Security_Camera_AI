import sys
import os
import threading
import uvicorn
import logging
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

# 1. Замын тохиргоог Root түвшинд тохируулах
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 2. Апп-аа үүсгэх (app/api/api.py-аас импортлохын оронд энд шууд тохируулж болно)
from app.api.api import app 

# 3. Үйлчилгээнүүдийг импортлох
from app.services.camera_service import video_capture
from app.services.alert_service import alert_worker
from app.services.ai_service import ai_inference

# 4. Router-уудыг холбох (auth.py-ийг саяны зассан хувилбараар ашиглана)
from app.api.auth import router as auth_router
# Хэрэв password болон camera тусдаа router бол эдгээрийг асааж болно
# from app.api.password import router as password_router
# from app.api.camera import router as camera_router

# CORS тохиргоо (Frontend болон Backend холболтонд чухал)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router-үүдийг бүртгэх
app.include_router(auth_router)
# app.include_router(password_router)
# app.include_router(camera_router)

# --- АЛЕРТЫН ЗУРАГ ХАДГАЛАХ ХАВТАС ---
ALERTS_DIR = os.path.join(BASE_DIR, "alerts")
if not os.path.exists(ALERTS_DIR):
    os.makedirs(ALERTS_DIR)
app.mount("/static", StaticFiles(directory=ALERTS_DIR), name="static")

# --- FRONTEND (REACT DIST) ХОЛБОХ ХЭСЭГ ---

dist_path = os.path.join(BASE_DIR, "dist")

if os.path.exists(dist_path):
    # assets хавтсыг mount хийх
    assets_path = os.path.join(dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        # API хүсэлт болон Видео стримийг алгасах
        api_prefixes = ["auth", "api", "video_feed", "static", "assets", "token"]
        if any(catchall.startswith(prefix) for prefix in api_prefixes):
            return None # FastAPI-ийн өөрийн замууд руу шилжинэ
            
        return FileResponse(os.path.join(dist_path, "index.html"))
else:
    print(f"!!! АНХААР: {dist_path} олдсонгүй. Frontend ажиллахгүй.")

# --- СЕРВЕР АСААХ ХЭСЭГ ---

if __name__ == "__main__":
    # Railway-ийн портыг авах
    port = int(os.getenv("PORT", 8000))
    
    print(f"--- Chipmo Security AI Port:{port} дээр ажиллаж эхэллээ ---")

    # Background Thread-үүдийг асаах
    # daemon=True нь main thread зогсоход хамт зогсоно
    try:
        threading.Thread(target=video_capture, daemon=True).start()
        threading.Thread(target=alert_worker, daemon=True).start()
        threading.Thread(target=ai_inference, daemon=True).start()
        print("Камер, Alert, AI үйлчилгээнүүд background-д асаалаа.")
    except Exception as e:
        print(f"Background үйлчилгээ асаахад алдаа гарлаа: {e}")

    # Uvicorn ажиллуулах
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
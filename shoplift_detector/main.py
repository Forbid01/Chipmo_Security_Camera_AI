import sys
import os
import threading
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI

# 1. Замын тохиргоог маш тодорхой болгох
# main.py байгаа хавтас (Root эсвэл app хавтас)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Үндсэн FastAPI app-г импортлох
from app.api.api import app 

# Үйлчилгээнүүдийг импортлох
from app.services.camera_service import video_capture
from app.services.alert_service import alert_worker
from app.services.ai_service import ai_inference

# Router-уудыг холбох
from app.api.auth import router as auth_router
from app.api.password import router as password_router
from app.api.camera import router as camera_router

app.include_router(auth_router)
app.include_router(password_router)
app.include_router(camera_router)

# --- FRONTEND ХОЛБОХ ХЭСЭГ (API-УУДЫН ДАРАА БАЙХ ЁСТОЙ) ---

# dist хавтас main.py-тай ижил түвшинд байгаа гэж үзэв
dist_path = os.path.join(BASE_DIR, "dist")

if os.path.exists(dist_path):
    # CSS, JS файлуудыг холбох
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")

    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        # API хүсэлтүүд болон видео feed-ийг алгасах (Эдгээр нь замаар орж ирвэл React руу явуулахгүй)
        api_endpoints = ["api", "video_feed", "forgot-password", "verify-code", "reset-password"]
        if any(endpoint in catchall for endpoint in api_endpoints):
            return None # FastAPI өөрийн router-ээрээ шийднэ
            
        return FileResponse(os.path.join(dist_path, "index.html"))
else:
    print(f"!!! АНХААР: {dist_path} олдсонгүй. Frontend ажиллахгүй.")

# --- СЕРВЕР АСААХ ХЭСЭГ ---

if __name__ == "__main__":
    # Railway-ийн портыг авах
    port = int(os.getenv("PORT", 8000))
    
    print(f"--- Shoplift Detector Систем Port:{port} дээр ажиллаж эхэллээ ---")

    # Background Thread-үүдийг uvicorn-оос ӨМНӨ асаах ёстой
    threading.Thread(target=video_capture, daemon=True).start()
    threading.Thread(target=alert_worker, daemon=True).start()
    threading.Thread(target=ai_inference, daemon=True).start()

    print(" Камер, Alert, AI үйлчилгээнүүд асаалаа.")
    
    # Хамгийн сүүлд uvicorn-оо асаана
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
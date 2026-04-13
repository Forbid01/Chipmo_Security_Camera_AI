import sys
import os
import threading
import uvicorn

# Замын тохиргоо
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Үндсэн FastAPI app-г api.py-аас импортлох
from app.api.api import app

# Үйлчилгээнүүдийг импортлох
from app.services.camera_service import video_capture
from app.services.alert_service import alert_worker
from app.services.ai_service import ai_inference

# Нэмэлт router-уудыг холбох
from app.api.auth import router as auth_router
from app.api.password import router as password_router
from app.api.camera import router as camera_router

app.include_router(auth_router)
app.include_router(password_router)
app.include_router(camera_router)

# Тэмдэглэл: CORS api.py-д аль хэдийн тохируулагдсан тул давхардуулахгүй

dist_path = os.path.join(current_dir, "dist")

if os.path.exists(dist_path):
    # CSS, JS файлуудыг /assets замаар уншина
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")

    # Вэб рүү ороход (/) шууд index.html-ийг өгнө
    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        # Хэрэв API биш бол React-ийн index.html-ийг буцаана (Single Page App routing)
        if catchall.startswith("api") or catchall in ["video_feed", "forgot-password", "verify-code", "reset-password"]:
             return None # API-ууд хэвийн ажиллана
        return FileResponse(os.path.join(dist_path, "index.html"))
else:
    print(" АНХААР: 'dist' хавтас олдсонгүй. Frontend ажиллахгүй байж магадгүй!")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f" Shoplift Detector Систем {port} порт дээр ажиллаж эхэллээ...")
    
    print(" Shoplift Detector Систем ажиллаж эхэллээ...")
    print("---")

    # Background Thread-үүд асаах
    threading.Thread(target=video_capture, daemon=True).start()
    print(" Камерын үйлчилгээ асалаа")

    threading.Thread(target=alert_worker, daemon=True).start()
    print(" Alert үйлчилгээ асалаа")

    threading.Thread(target=ai_inference, daemon=True).start()
    print(" AI үйлчилгээ асалаа")

    print("---")
    print(" API Server идэвхтэй: http://0.0.0.0:8000")
    print(" Видео дамжуулалт: http://0.0.0.0:8000/video_feed")
    print("---")
    
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
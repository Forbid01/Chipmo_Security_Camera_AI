import sys
import os
import threading
import uvicorn

# Замын тохиргоо
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

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

if __name__ == "__main__":
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

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
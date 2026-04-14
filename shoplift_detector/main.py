import sys
import os
import threading
import uvicorn
import logging
import logging.handlers
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from app.db.repository.users import UserRepository

# Logging тохиргоо
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            "app.log", maxBytes=10_000_000, backupCount=5
        ),
    ],
)
logger = logging.getLogger(__name__)

# 1. Замын тохиргоо
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 2. Үйлчилгээнүүдийг импортлох (Импортын алдаанаас сэргийлж дээр байрлуулна)
from app.api.api import app
from app.services.camera_service import video_capture
from app.services.alert_service import alert_worker
from app.services.ai_service import ai_inference

# --- BACKGROUND SERVICES ---
def start_background_tasks():
    try:
        # Daemon thread-үүд нь үндсэн программ зогсоход хамт зогсоно
        t1 = threading.Thread(target=video_capture, daemon=True)
        t2 = threading.Thread(target=alert_worker, daemon=True)
        t3 = threading.Thread(target=ai_inference, daemon=True)
        
        t1.start()
        t2.start()
        t3.start()
        logger.info("Background services (Camera, Alert, AI) started successfully.")
    except Exception as e:
        logger.error(f"Error starting background services: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # [STARTUP]
    logger.info("Initializing database...")
    try:
        repo = UserRepository()
        await repo._create_table()
    except Exception as e:
        logger.error(f"DB Init Error: {e}")

    logger.info("Starting background tasks...")
    start_background_tasks()
    
    yield

    # [SHUTDOWN]
    logger.info("Shutting down Chipmo AI...")

# Lifespan-ыг апп-д тохируулах
app.router.lifespan_context = lifespan

ALERTS_DIR = os.path.join(BASE_DIR, "alerts")
if not os.path.exists(ALERTS_DIR):
    os.makedirs(ALERTS_DIR)

# Static болон Assets хавтаснуудыг mount хийх
app.mount("/static", StaticFiles(directory=ALERTS_DIR), name="static")

dist_path = os.path.join(BASE_DIR, "dist")
if os.path.exists(dist_path):
    assets_path = os.path.join(dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        api_prefixes = ["auth", "api", "video_feed", "static", "assets", "token", "health", "docs", "redoc", "openapi.json", "users", "admin", "register", "login", "forgot-password", "verify-code", "reset-password", "alerts"]
        if any(catchall.startswith(prefix) for prefix in api_prefixes):
            # Энэ хэсэгт FastAPI өөрөө Router-ээс замаа хайхыг зөвшөөрнө
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
            
        index_file = os.path.join(dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"error": "Frontend build not found"}
else:
    logger.warning("Frontend 'dist' directory not found.")

# --- RUN SERVER ---

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting Chipmo Security AI on port: {port}")
    
    # Reload=True үед thread-үүд олон дахин асах аюултай тул deployment дээр False байлгана
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
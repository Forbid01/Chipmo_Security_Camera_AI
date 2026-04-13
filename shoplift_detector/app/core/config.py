import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# shoplift_detector фолдерын замыг олох (core хавтаснаас 2 түвшин дээш)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALERTS_DIR = os.path.join(BASE_DIR, "alerts")
FACES_DIR = os.path.join(BASE_DIR, "faces")

# Хавтаснуудыг автоматаар үүсгэх
for folder in [ALERTS_DIR, FACES_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# CORS зөвшөөрөгдсөн домэйнүүд
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '').split(',')
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]

# Камерын тохиргоо (.env-ээс авна)
WIFI_CAMERA_URL = os.getenv('WIFI_CAMERA_URL', '')
AXIS_CAMERA_URL = os.getenv('AXIS_CAMERA_URL', '')
MAC_CAMERA_INDEX = int(os.getenv('MAC_CAMERA_INDEX', '0'))

DEFAULT_CAMERA_SOURCES = {
    "mac": MAC_CAMERA_INDEX,
    "phone": WIFI_CAMERA_URL,
    "axis": AXIS_CAMERA_URL,
}

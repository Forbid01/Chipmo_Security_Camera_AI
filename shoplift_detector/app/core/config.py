import os
from dotenv import load_dotenv

load_dotenv()

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
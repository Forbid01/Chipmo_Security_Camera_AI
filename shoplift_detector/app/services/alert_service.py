import os
import cv2
import logging
import requests
import time
import subprocess
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from app.core.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from app.core.state import alert_queue

logger = logging.getLogger(__name__)

# Telegram API-д retry логик нэмэх
_session = requests.Session()
_retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
_session.mount("https://", HTTPAdapter(max_retries=_retry))

def save_video_optimized(frames, output_path):
    if not frames or len(frames) == 0:
        return False

    temp_raw_path = output_path.replace(".mp4", "_raw.mp4")
    
    try:
        height, width, _ = frames[0].shape
        fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
        out = cv2.VideoWriter(temp_raw_path, fourcc, 20.0, (width, height))
        
        for f in frames:
            out.write(f)
        out.release()

        cmd = [
            'ffmpeg', '-y', 
            '-i', temp_raw_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '28',
            '-pix_fmt', 'yuv420p',
            '-movflags', 'faststart',
            '-an',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg Error: {result.stderr}")
            return False

        if os.path.exists(temp_raw_path):
            os.remove(temp_raw_path)
        
        return True
        
    except Exception as e:
        logger.error(f"Video Save Error: {e}")
        if os.path.exists(temp_raw_path):
            os.remove(temp_raw_path)
        return False
    
def send_telegram_photo(token, chat_id, photo_path, caption):
    """Зураг Telegram-руу илгээх (retry логиктой)"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as p:
            r = _session.post(url, data={
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'Markdown'
            }, files={'photo': p}, timeout=30)
        logger.info(f"Telegram Зураг: {r.json().get('ok')}")
        return r.json().get('ok', False)
    except Exception as e:
        logger.error(f"Telegram Зураг алдаа: {e}")
        return False


def send_telegram_video(token, chat_id, video_path, caption):
    """Видео Telegram-руу илгээх (retry логиктой)"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendVideo"
        with open(video_path, 'rb') as v:
            r = _session.post(url, data={
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'Markdown'
            }, files={'video': v}, timeout=60)
        logger.info(f"Telegram Видео: {r.json().get('ok')}")
        return r.json().get('ok', False)
    except Exception as e:
        logger.error(f"Telegram Видео алдаа: {e}")
        return False


def alert_worker():

    while True:
        data = alert_queue.get()
        logger.info(f"Alert дата ирлээ: id={data.get('id')} reason={data.get('reason')}")

        try:
            frame = data.get('frame')
            if frame is None:
                frame = cv2.imread(data['img'])
            else:
                frame = frame.copy()

            tg_photo_path = data['img'].replace('.jpg', '_tg.jpg')

            if 'bbox' in data:
                x1, y1, x2, y2 = map(int, data['bbox'])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)

                h, w = frame.shape[:2]
                pad = int((x2 - x1) * 0.4)
                cx1 = max(0, x1 - pad)
                cy1 = max(0, y1 - pad)
                cx2 = min(w, x2 + pad)
                cy2 = min(h, y2 + pad)

                telegram_img = frame[cy1:cy2, cx1:cx2]
                if telegram_img.size > 0:
                    cv2.imwrite(tg_photo_path, telegram_img)
                else:
                    cv2.imwrite(tg_photo_path, frame)
            else:
                cv2.imwrite(tg_photo_path, frame)

            cv2.imwrite(data['img'], frame)

            # --- 2. VIDEO ---
            video_path = data['img'].replace('.jpg', '.mp4')
            video_saved = False
            if 'clip' in data and data['clip']:
                video_saved = save_video_optimized(data['clip'], video_path)
            elif os.path.exists(video_path):
                video_saved = True

            # --- 3. TELEGRAM ---
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            caption = (
                f" *СЭЖИГТЭЙ ҮЙЛДЭЛ ИЛЭРЛЭЭ*\n\n"
                f" *Нэр:* {data.get('name', 'Unknown')}\n"
                f" *ID:* `{data.get('id', 'N/A')}`\n"
                f" *Шалтгаан:* {data.get('reason', '')}\n"
                f" *Цаг:* {timestamp}"
            )

            # Token хоосон эсэхийг шалгах
            if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
                logger.warning("Telegram TOKEN эсвэл CHAT_ID тохируулаагүй байна.")
            else:
                if video_saved and os.path.exists(video_path):
                    ok = send_telegram_video(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, video_path, caption)
                    if not ok:
                        # Видео явуулж чадахгүй бол зураг явуулна
                        send_telegram_photo(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, tg_photo_path, caption)
                else:
                    send_telegram_photo(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, tg_photo_path, caption)

            if os.path.exists(tg_photo_path):
                os.remove(tg_photo_path)

        except Exception as e:
            logger.error(f"Alert Worker алдаа: {e}", exc_info=True)
        finally:
            alert_queue.task_done()
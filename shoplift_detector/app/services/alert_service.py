import logging
import os
import subprocess
import tempfile
import time

import cv2
from app.core.config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from app.core.state import alert_queue

logger = logging.getLogger(__name__)


def _is_remote_url(path: str) -> bool:
    return isinstance(path, str) and path.startswith(("http://", "https://"))

_session = None


def _get_requests_session():
    """Telegram API-д retry логиктой lazy session үүсгэнэ.

    Keep this lazy so importing the FastAPI app in tests does not require the
    optional Telegram HTTP dependency unless notifications are actually sent.
    """
    global _session
    if _session is not None:
        return _session

    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except ImportError:
        logger.warning("requests dependency missing; Telegram alert sending disabled")
        return None

    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    _session = session
    return session

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
        session = _get_requests_session()
        if session is None:
            return False

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as p:
            r = session.post(url, data={
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
        session = _get_requests_session()
        if session is None:
            return False

        url = f"https://api.telegram.org/bot{token}/sendVideo"
        with open(video_path, 'rb') as v:
            r = session.post(url, data={
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
            img_ref = data.get('img', '')
            if frame is None and not _is_remote_url(img_ref) and os.path.exists(img_ref):
                frame = cv2.imread(img_ref)
            if frame is None:
                logger.warning("Alert worker: no frame available, skipping Telegram")
                continue
            frame = frame.copy()

            with tempfile.NamedTemporaryFile(suffix="_tg.jpg", delete=False) as tf:
                tg_photo_path = tf.name

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

            # --- 2. VIDEO ---
            video_path = None
            video_saved = False
            if 'clip' in data and data['clip']:
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
                    video_path = vf.name
                video_saved = save_video_optimized(data['clip'], video_path)

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
                if video_saved and video_path and os.path.exists(video_path):
                    ok = send_telegram_video(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, video_path, caption)
                    if not ok:
                        # Видео явуулж чадахгүй бол зураг явуулна
                        send_telegram_photo(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, tg_photo_path, caption)
                else:
                    send_telegram_photo(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, tg_photo_path, caption)

            if tg_photo_path and os.path.exists(tg_photo_path):
                os.remove(tg_photo_path)
            if video_path and os.path.exists(video_path):
                os.remove(video_path)

        except Exception as e:
            logger.error(f"Alert Worker алдаа: {e}", exc_info=True)
        finally:
            alert_queue.task_done()

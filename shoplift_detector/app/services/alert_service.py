import os
import cv2
import requests
import time
import subprocess
from app.core.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from app.core.state import alert_queue

def save_video_optimized(frames, output_path):
    """Видеог avc1 кодекоор хадгалаад, FFmpeg-ээр вэбэд зориулж оновчлох"""
    if not frames or len(frames) == 0: 
        return False
    
    temp_raw_path = output_path.replace(".mp4", "_raw.mp4")
    try:
        height, width, _ = frames[0].shape
        # 1. Анхны хадгалалт (avc1 ашиглана)
        fourcc = cv2.VideoWriter_fourcc(*'avc1') 
        out = cv2.VideoWriter(temp_raw_path, fourcc, 20.0, (width, height))
        for f in frames: 
            out.write(f)
        out.release()

        # 2. FFmpeg-ээр "faststart" болон вэб формат руу хөрвүүлэх (МАШ ЧУХАЛ)
        # Энэ алхам байхгүй бол браузер дээр тоглохгүй
        cmd = [
            'ffmpeg', '-y', '-i', temp_raw_path,
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-movflags', 'faststart', '-an',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        
        if os.path.exists(temp_raw_path):
            os.remove(temp_raw_path)
        return True
    except Exception as e: 
        print(f"  Video Save/Optimize Error: {e}")
        if os.path.exists(temp_raw_path): os.remove(temp_raw_path)
        return False

def alert_worker():
    print("  Alert Worker идэвхтэй ажиллаж байна...")
    while True:
        data = alert_queue.get()
        try:
            # ai_service-аас bbox + frame ирэх ёстой (smart-crop хийхэд).
            # Гэхдээ хуучин payload ирсэн тохиолдолд зурагнаас fallback хийнэ.
            frame = data.get('frame')
            if frame is None:
                frame = cv2.imread(data['img'])
            else:
                frame = frame.copy()
            tg_photo_path = data['img'].replace('.jpg', '_tg.jpg')
            
            # --- 1. SMART CROP & DRAW ---
            if 'bbox' in data:
                x1, y1, x2, y2 = map(int, data['bbox'])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                
                h, w = frame.shape[:2]
                pad = int((x2 - x1) * 0.4) 
                cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
                cx2, cy2 = min(w, x2 + pad), min(h, y2 + pad)
                
                telegram_img = frame[cy1:cy2, cx1:cx2]
                if telegram_img.size > 0:
                    cv2.imwrite(tg_photo_path, telegram_img)
                else:
                    cv2.imwrite(tg_photo_path, frame)
            else:
                cv2.imwrite(tg_photo_path, frame)

            cv2.imwrite(data['img'], frame)

            # --- 2. OPTIMIZED VIDEO CLIP ---
            # Чиний Dashboard-ын URL энэ video_path-ыг дуудаж байгаа тул энд заавал оновчлох ёстой
            video_path = data['img'].replace('.jpg', '.mp4')
            video_saved = False
            if 'clip' in data and data['clip']:
                # Урьдчилан нийлүүлсэн frames байвал дахин encode хийнэ.
                video_saved = save_video_optimized(data['clip'], video_path)
            else:
                # ai_service аль хэдийн mp4 үүсгэсэн байж болно.
                video_saved = True if os.path.exists(video_path) else False

            # --- 3. TELEGRAM SENDING ---
            if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
                timestamp = time.strftime('%H:%M:%S')
                msg_text = (
                    f" *СЭЖИГТЭЙ ҮЙЛДЭЛ ИЛЭРЛЭЭ*\n\n"
                    f" *Нэр:* {data.get('name', 'Unknown')}\n"
                    f" *ID:* `{data.get('id', 'N/A')}`\n"
                    f" *Цаг:* {timestamp}"
                )

                if video_saved and os.path.exists(video_path):
                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo"
                    with open(video_path, 'rb') as v:
                        requests.post(url, data={
                            'chat_id': TELEGRAM_CHAT_ID, 
                            'caption': msg_text,
                            'parse_mode': 'Markdown'
                        }, files={'video': v}, timeout=45) # Видео явуулахад timeout-ыг жаахан сунгав
                else:
                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                    with open(tg_photo_path, 'rb') as p:
                        requests.post(url, data={
                            'chat_id': TELEGRAM_CHAT_ID, 
                            'caption': msg_text,
                            'parse_mode': 'Markdown'
                        }, files={'photo': p}, timeout=30)
                
                if os.path.exists(tg_photo_path): os.remove(tg_photo_path)
                print(f"  Telegram Alert Sent: {data.get('name')}")
            
        except Exception as e: 
            print(f"  Alert Worker Error: {e}")
        finally:
            alert_queue.task_done()
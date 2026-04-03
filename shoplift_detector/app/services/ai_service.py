import os
import cv2
import torch
import queue
import time
import numpy as np
import math
import warnings
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor

from ultralytics import YOLO
from insightface.app import FaceAnalysis

from app.core.config import FACES_DIR, ALERTS_DIR
from app.core.state import (
    ai_input_queue, alert_queue, video_buffer, buffer_lock,
    safe_update_display_queue
)
from app.db.repository.alerts import AlertRepository

# Keypoint-ийн confidence босго — YOLO [0,0] буцаахаас сэргийлэх
KEYPOINT_CONF_THRESHOLD = 0.3

# Хэдэн фрейм харагдаагүй бол track устгах
STALE_TRACK_FRAMES = 150  # ~5 секунд 30FPS-т

# Оноо задрах коэффициент (фрейм тутамд)
SCORE_DECAY = 0.98

# Сэрэмжлүүлэгийн хооронд дахин дуугарахгүй байх хугацаа (секунд)
ALERT_COOLDOWN = 15

# Оноог нэмэх утгууд
SCORE_CAMERA_CHECK  = 0.4
SCORE_ITEM_PICKUP   = 25.0
SCORE_CONCEALMENT   = 35.0
SCORE_ALERT_TRIGGER = 50.0


class ShopliftDetector:
    def __init__(self, device_type: str):
        self.device = device_type
        self.alert_db = AlertRepository()
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Моделиудыг ачааллах
        self.pose_model = YOLO("yolo11m-pose.pt").to(self.device)
        self.det_model  = YOLO("yolo11n.pt").to(self.device)

        # Царайны таних — одоо ашиглагдахгүй байгаа ч ирээдүйд хэрэгтэй
        # self.face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        # self.face_app.prepare(ctx_id=0, det_size=(640, 640))

        self.tracker_history: dict = {}
        self.last_alert_time: dict = {}
        self.frame_count = 0

        # Сүүлийн object detection үр дүнг cache хийх (3 фрейм тутамд шинэчлэнэ)
        self._cached_expensive_items: list = []

    # ------------------------------------------------------------------ #
    #  Хувийн туслах аргууд
    # ------------------------------------------------------------------ #

    def _optimize_video(self, video_path: str):
        """FFmpeg ашиглан бичлэгийг вэб болон MacOS-д зориулж хөрвүүлэх."""
        temp_path = video_path.replace(".mp4", "_temp.mp4")
        try:
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "faststart", "-an",
                temp_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            os.replace(temp_path, video_path)
        except Exception as e:
            print(f"[FFmpeg] Алдаа: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _async_save_alert(self, yolo_id, frame_to_save, name: str, reason: str, bbox: list):
        """
        Сэжигтэй үйлдлийг тасдаж хадгалах (Background thread).
        frame_to_save нь .copy() хийгдсэн байна — race condition байхгүй.
        """
        try:
            current_time = int(time.time())
            base_filename = f"alert_{yolo_id}_{current_time}"
            img_path   = os.path.join(ALERTS_DIR, f"{base_filename}.jpg")
            video_path = os.path.join(ALERTS_DIR, f"{base_filename}.mp4")

            cv2.imwrite(img_path, frame_to_save)

            with buffer_lock:
                frames_snapshot = list(video_buffer)

            if frames_snapshot:
                height, width, _ = frames_snapshot[0].shape
                fourcc = cv2.VideoWriter_fourcc(*"avc1")
                out = cv2.VideoWriter(video_path, fourcc, 20.0, (width, height))
                for f in frames_snapshot:
                    out.write(f)
                out.release()
                self._optimize_video(video_path)

            self.alert_db.insert_alert(
                person_id=int(yolo_id),
                image_path=img_path,
                reason=reason,
            )
            alert_queue.put({
                "id":        yolo_id,
                "video_url": f"/static/alerts/{base_filename}.mp4",
                "img":       img_path,
                "reason":    reason,
                "name":      name,
                # Telegram smart-crop болон box зурахад шаардлагатай мэдээлэл
                "frame":     frame_to_save,
                "bbox":      bbox,
            })
        except Exception as e:
            print(f"[Alert] Хадгалах алдаа: {e}")

    @staticmethod
    def _keypoint_valid(kp) -> bool:
        """YOLO [0,0] буцаах үед буруу тооцоолохоос сэргийлэх."""
        return kp[0] > 1.0 and kp[1] > 1.0

    def _cleanup_stale_tracks(self):
        """Удаан харагдаагүй track-уудыг устгах — RAM хэмнэх."""
        stale_ids = [
            tid for tid, data in self.tracker_history.items()
            if self.frame_count - data["last_seen"] > STALE_TRACK_FRAMES
        ]
        for tid in stale_ids:
            del self.tracker_history[tid]
            self.last_alert_time.pop(tid, None)

    def run_inference(self):
        while True:
            try:
                frame = ai_input_queue.get(timeout=2)
            except queue.Empty:
                continue

            display_frame = frame.copy()
            current_time  = time.time()
            self.frame_count += 1

            if self.frame_count % 50 == 0:
                self._cleanup_stale_tracks()

            pose_results = self.pose_model.track(
                frame, persist=True, device=self.device, verbose=False, imgsz=320
            )

            if self.frame_count % 3 == 0:
                self._cached_expensive_items = []
                det_results = self.det_model.predict(
                    frame, conf=0.4, device=self.device, verbose=False
                )
                if det_results[0].boxes is not None:
                    for box in det_results[0].boxes:
                        label = self.det_model.names[int(box.cls[0])]
                        if label in ["cell phone", "bottle", "handbag", "laptop"]:
                            self._cached_expensive_items.append({
                                "box":   box.xyxy[0].cpu().numpy(),
                                "label": label,
                            })

            expensive_items = self._cached_expensive_items

            if pose_results[0].boxes.id is not None:
                yolo_ids   = pose_results[0].boxes.id.int().cpu().numpy()
                keypoints  = pose_results[0].keypoints.xy.cpu().numpy()
                boxes      = pose_results[0].boxes.xyxy.cpu().numpy()

                for i, yolo_id in enumerate(yolo_ids):
                    x1, y1, x2, y2 = map(int, boxes[i])
                    person_h = max(1, y2 - y1)

                    if yolo_id not in self.tracker_history:
                        self.tracker_history[yolo_id] = {
                            "holding":   None,
                            "score":     0.0,
                            "last_seen": self.frame_count,
                        }

                    curr = self.tracker_history[yolo_id]
                    curr["last_seen"] = self.frame_count
                    curr["score"] = max(0.0, curr["score"] * SCORE_DECAY)

                    if len(keypoints[i]) > 11:
                        nose     = keypoints[i][0]
                        wrist    = keypoints[i][9]
                        shoulder = keypoints[i][11]

                        if self._keypoint_valid(nose) and self._keypoint_valid(shoulder):
                            if abs(nose[0] - shoulder[0]) > (person_h * 0.12):
                                curr["score"] += SCORE_CAMERA_CHECK

                        if self._keypoint_valid(wrist):
                            for item in expensive_items:
                                ix1, iy1, ix2, iy2 = item["box"]
                                if ix1 < wrist[0] < ix2 and iy1 < wrist[1] < iy2:
                                    if not curr["holding"]:
                                        curr["holding"] = item["label"]
                                        curr["score"]  += SCORE_ITEM_PICKUP

                            if curr["holding"] and self._keypoint_valid(shoulder):
                                dist = math.dist(wrist, shoulder)
                                if dist < (person_h * 0.18):
                                    curr["score"] += SCORE_CONCEALMENT

                                    if curr["score"] >= SCORE_ALERT_TRIGGER:
                                        last_alert = self.last_alert_time.get(yolo_id, 0)
                                        if current_time - last_alert > ALERT_COOLDOWN:
                                            reason = f"{curr['holding']} нуусан үйлдэл"
                                            self.executor.submit(
                                                self._async_save_alert,
                                                yolo_id,
                                                display_frame.copy(),
                                                "Unknown",
                                                reason,
                                                [x1, y1, x2, y2],
                                            )
                                            self.last_alert_time[yolo_id] = current_time
                                            curr["score"]   = 0.0
                                            curr["holding"] = None

                    score_color = (0, 255, 0) if curr["score"] < 30 else (0, 165, 255) if curr["score"] < 50 else (0, 0, 255)
                    cv2.putText(
                        display_frame,
                        f"ID:{yolo_id} Score:{int(curr['score'])}",
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        score_color,
                        2,
                    )
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), score_color, 2)

            safe_update_display_queue(display_frame)


# ------------------------------------------------------------------ #
#  main.py-с дуудах entry-point функц
#  threading.Thread(target=ai_inference, daemon=True).start()
# ------------------------------------------------------------------ #

def ai_inference():
    """
    AI inference thread-ийн эхлэл цэг.
    Төхөөрөмжийг автоматаар тодорхойлж ShopliftDetector-ийг ажиллуулна.
    """
    device = "mps" if torch.backends.mps.is_available() else \
             "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[AI] Төхөөрөмж: {device}")
    detector = ShopliftDetector(device_type=device)
    detector.run_inference()
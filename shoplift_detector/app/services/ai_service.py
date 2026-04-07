# app/services/ai_service.py

import os
import cv2
import torch
import queue
import time
import numpy as np
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor
from ultralytics import YOLO

try:
    from app.core.config import ALERTS_DIR
    from app.core.state import (
        ai_input_queue, alert_queue, video_buffer, buffer_lock,
        safe_update_display_queue
    )
    from app.db.repository.alerts import AlertRepository
except ImportError:
    print("Анхаар: app.core модулиуд олдохгүй байна.")

STALE_TRACK_FRAMES  = 150
SCORE_DECAY         = 0.98
ALERT_COOLDOWN      = 15
SCORE_ALERT_TRIGGER = 80  # ← Өндөр байх тусам алдаа бага

# --- Оноо өгөх систем ---
SCORE_LOOKING_AROUND   = 1.5   # Орчноо эргэн харах
SCORE_ITEM_PICKUP      = 15.0  # Барааг гараар хүрэх
SCORE_BODY_BLOCK       = 3.0   # Биеэр бараагаа далдлах
SCORE_CROUCH           = 1.0   # Бөхийх (далдлах зорилгоор)
SCORE_WRIST_TO_TORSO   = 5.0   # Гарыг биеийн дотогш татах
SCORE_RAPID_MOVEMENT   = 1.5   # Гарын хурдан хөдөлгөөн


class ShopliftDetector:
    def __init__(self, device_type: str):
        self.device = device_type
        self.alert_db = AlertRepository()
        self.executor = ThreadPoolExecutor(max_workers=4)

        self.pose_model = YOLO("yolo11m-pose.pt").to(self.device)
        self.det_model  = YOLO("yolo11n.pt").to(self.device)

        self.tracker_history: dict = {}
        self.last_alert_time: dict = {}
        self.frame_count = 0
        self._cached_expensive_items: list = []

    def _optimize_video(self, video_path: str):
        temp_path = video_path.replace(".mp4", "_temp.mp4")
        try:
            cmd = [
                "ffmpeg", "-y", "-threads", "2", "-i", video_path,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p", "-movflags", "faststart", "-an",
                temp_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            os.replace(temp_path, video_path)
        except Exception as e:
            print(f"[FFmpeg] Алдаа: {e}")

    def _async_save_alert(self, yolo_id, frame_to_save, name: str, reason: str, bbox: list):
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
                person_id=int(yolo_id), image_path=img_path, reason=reason
            )
            alert_queue.put({
                "id": yolo_id,
                "video_url": f"/static/alerts/{base_filename}.mp4",
                "img": img_path, "reason": reason, "name": name,
                "frame": frame_to_save, "bbox": bbox,
            })
        except Exception as e:
            print(f"[Alert] Хадгалах алдаа: {e}")

    @staticmethod
    def _keypoint_valid(kp) -> bool:
        return kp[0] > 1.0 and kp[1] > 1.0

    def _cleanup_stale_tracks(self):
        stale_ids = [
            tid for tid, data in self.tracker_history.items()
            if self.frame_count - data["last_seen"] > STALE_TRACK_FRAMES
        ]
        for tid in stale_ids:
            del self.tracker_history[tid]
            self.last_alert_time.pop(tid, None)

    def _analyze_behavior(self, curr: dict, kps, person_h: float, expensive_items: list):
        """
        Хүний keypoint-уудаас сэжигтэй үйлдлийг шинжлэх.
        Буцаах утга: (нэмэгдэх оноо, шалтгааны жагсаалт)
        """
        score_delta = 0.0
        reasons = []

        if len(kps) < 17:
            return score_delta, reasons

        nose       = kps[0]
        l_eye      = kps[1]
        r_eye      = kps[2]
        l_shoulder = kps[5]
        r_shoulder = kps[6]
        l_elbow    = kps[7]
        r_elbow    = kps[8]
        l_wrist    = kps[9]
        r_wrist    = kps[10]
        l_hip      = kps[11]
        r_hip      = kps[12]
        l_knee     = kps[13]
        r_knee     = kps[14]

        # Мөрний төв
        shoulder_cx = None
        if self._keypoint_valid(l_shoulder) and self._keypoint_valid(r_shoulder):
            shoulder_cx = (l_shoulder[0] + r_shoulder[0]) / 2
            shoulder_cy = (l_shoulder[1] + r_shoulder[1]) / 2
        
        # Нүүрний төв
        face_cx = None
        if self._keypoint_valid(l_eye) and self._keypoint_valid(r_eye):
            face_cx = (l_eye[0] + r_eye[0]) / 2

        # Дундаж хип
        hip_cy = None
        if self._keypoint_valid(l_hip) and self._keypoint_valid(r_hip):
            hip_cy = (l_hip[1] + r_hip[1]) / 2

        # ① Орчноо эргэн харах — толгой мөрнөөс хажуу тийш хазайсан
        if face_cx is not None and shoulder_cx is not None:
            offset = abs(face_cx - shoulder_cx)
            if offset > person_h * 0.15:
                score_delta += SCORE_LOOKING_AROUND
                reasons.append(" Орчноо харах")

        # ② Гар барааны хайрцагт хүрэх
        for wrist in [l_wrist, r_wrist]:
            if not self._keypoint_valid(wrist):
                continue
            if not curr["holding"]:
                for item in expensive_items:
                    ix1, iy1, ix2, iy2 = item["box"]
                    if ix1 < wrist[0] < ix2 and iy1 < wrist[1] < iy2:
                        curr["holding"] = item["label"]
                        score_delta += SCORE_ITEM_PICKUP
                        reasons.append(f" {item['label']} авах")
                        break

        # ③ Биеэр бараагаа далдлах — мөрний өргөн агшсан (камер руу эргэсэн)
        if self._keypoint_valid(l_shoulder) and self._keypoint_valid(r_shoulder):
            shoulder_width = abs(r_shoulder[0] - l_shoulder[0])
            # Хэвийн өргөн person_h * 0.4 орчим байдаг
            # Камер руу эргэхэд өргөн агших
            if curr.get("avg_shoulder_w") is None:
                curr["avg_shoulder_w"] = shoulder_width
            else:
                curr["avg_shoulder_w"] = curr["avg_shoulder_w"] * 0.9 + shoulder_width * 0.1
                if shoulder_width < curr["avg_shoulder_w"] * 0.55:
                    score_delta += SCORE_BODY_BLOCK
                    reasons.append(" Биеэр далдлах")

        # ④ Бөхийх — хип мөрний доор хэт ойртсон (өндрийн 30%-иас бага зай)
        if hip_cy is not None and shoulder_cx is not None:
            torso_h = abs(hip_cy - l_shoulder[1])
            if torso_h < person_h * 0.15:
                if curr["holding"]:
                    score_delta += 5.0
                    reasons.append(" Бөхийж бараа нуух")
                else:
                    score_delta += SCORE_CROUCH
                    reasons.append(" Бөхийх")

        # ⑤ Гарыг биеийн дотогш татах — holding үед гарыг хип-ийн ойролцоо татах
        if curr["holding"] and hip_cy is not None:
            for wrist in [l_wrist, r_wrist]:
                if not self._keypoint_valid(wrist):
                    continue
                # Гар хип-ийн ойролцоо + биений дотор талд байвал нуусан гэж үзнэ
                wrist_to_hip = abs(wrist[1] - hip_cy)
                if wrist_to_hip < person_h * 0.15:
                    curr["concealment_frames"] += 1
                    if curr["concealment_frames"] % 8 == 0:
                        score_delta += SCORE_WRIST_TO_TORSO
                        reasons.append(f" Хувцас доор нуух ({curr['concealment_frames']}f)")
                else:
                    curr["concealment_frames"] = max(0, curr["concealment_frames"] - 1)

        # ⑥ Гарын хурдан хөдөлгөөн — holding үед гар огцом хөдөлсөн
        if curr["holding"]:
            for wrist, key in [(l_wrist, "prev_l_wrist"), (r_wrist, "prev_r_wrist")]:
                if not self._keypoint_valid(wrist):
                    continue
                prev = curr.get(key)
                if prev is not None:
                    speed = math.dist(wrist, prev)
                    # Хэвийн хөдөлгөөн person_h * 0.05-аас бага
                    if speed > person_h * 0.08:
                        score_delta += SCORE_RAPID_MOVEMENT
                        reasons.append("Хурдан хөдөлгөөн")
                curr[key] = tuple(wrist)

        return score_delta, reasons
    def run_inference(self):
        frame_counters = {
                "Mac-Camera": 0,
                "Axis-Camera": 0,
        }
        last_display_frames = {
            "Mac-Camera": None,
            "Axis-Camera": None,
        }

        while True:
            try:
                data = ai_input_queue.get(timeout=2)
                frame = data["frame"]
                source_name = data["source"]
            except (queue.Empty, TypeError, KeyError):
                continue
            
            frame_counters[source_name] = frame_counters.get(source_name, 0) + 1
            frame_idx = frame_counters[source_name]

            if frame_idx % 2 != 0:
                prev = last_display_frames.get(source_name)
                safe_update_display_queue(
                    prev if prev is not None else frame,
                    source=source_name
                )
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
                        lbl = self.det_model.names[int(box.cls[0])]
                        if lbl in ["cell phone", "bottle", "handbag", "laptop"]:
                            self._cached_expensive_items.append({
                                "box": box.xyxy[0].cpu().numpy(), "label": lbl
                            })

            expensive_items = self._cached_expensive_items

            if pose_results[0].boxes.id is not None:
                yolo_ids  = pose_results[0].boxes.id.int().cpu().numpy()
                keypoints = pose_results[0].keypoints.xy.cpu().numpy()
                boxes     = pose_results[0].boxes.xyxy.cpu().numpy()

                for i, yolo_id in enumerate(yolo_ids):
                    x1, y1, x2, y2 = map(int, boxes[i])
                    person_h = max(1, y2 - y1)

                    if yolo_id not in self.tracker_history:
                        self.tracker_history[yolo_id] = {
                            "holding": None,
                            "score": 0.0,
                            "last_seen": self.frame_count,
                            "concealment_frames": 0,
                            "avg_shoulder_w": None,
                            "prev_l_wrist": None,
                            "prev_r_wrist": None,
                            "last_reasons": [],
                        }

                    curr = self.tracker_history[yolo_id]
                    curr["last_seen"] = self.frame_count

                    if not curr["holding"]:
                        curr["score"] = max(0.0, curr["score"] * SCORE_DECAY)
                    else:
                        curr["score"] = max(0.0, curr["score"] * 0.999)

                    delta, reasons = self._analyze_behavior(
                        curr, keypoints[i], person_h, expensive_items
                    )
                    curr["score"] += delta
                    if reasons:
                        curr["last_reasons"] = reasons

                    if curr["score"] >= SCORE_ALERT_TRIGGER:
                        last_alert = self.last_alert_time.get(yolo_id, 0)
                        if current_time - last_alert > ALERT_COOLDOWN:
                            reason_str = " | ".join(curr["last_reasons"])
                            self.executor.submit(
                                self._async_save_alert,
                                yolo_id, display_frame.copy(),
                                "Unknown", f"🚨 {reason_str}", [x1, y1, x2, y2]
                            )
                            self.last_alert_time[yolo_id] = current_time
                            curr["score"] = 0.0
                            curr["holding"] = None
                            curr["concealment_frames"] = 0
                            curr["last_reasons"] = []

                    if curr["score"] < 25:
                        border_color, status_text = (0, 255, 0), "NORMAL"
                    elif curr["score"] < 55:
                        border_color, status_text = (0, 215, 255), "SUSPICIOUS"
                    else:
                        border_color, status_text = (0, 0, 255), "THEFT DETECTED"

                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), border_color, 2)
                    label = (
                        f"ID:{yolo_id} | {status_text} | "
                        f"S:{int(curr['score'])} F:{curr['concealment_frames']}"
                    )
                    (t_w, t_h), _ = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                    )
                    cv2.rectangle(
                        display_frame,
                        (x1, y1 - 25), (x1 + t_w + 10, y1),
                        border_color, -1
                    )
                    cv2.putText(
                        display_frame, label, (x1 + 5, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA
                    )

                    if curr["score"] >= 25 and curr["last_reasons"]:
                        reason_label = " | ".join(curr["last_reasons"][:2])
                        cv2.putText(
                            display_frame, reason_label,
                            (x1, y2 + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, border_color, 1, cv2.LINE_AA
                        )

            last_display_frames[source_name] = display_frame
            safe_update_display_queue(display_frame, source=source_name)
def ai_inference():
    device = (
        "mps" if torch.backends.mps.is_available()
        else "cuda" if torch.cuda.is_available()
        else "cpu"
    )
    print(f"[AI] Төхөөрөмж: {device}")
    detector = ShopliftDetector(device_type=device)
    detector.run_inference()
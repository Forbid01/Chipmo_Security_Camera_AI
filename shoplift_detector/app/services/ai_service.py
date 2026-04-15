# app/services/ai_service.py

import contextlib
import logging
import math
import os
import queue
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import torch
from ultralytics import YOLO

logger = logging.getLogger(__name__)

try:
    from app.core.config import ALERTS_DIR
    from app.services.auto_learner import auto_learner
    from app.services.camera_manager import camera_manager
except ImportError:
    logger.error("app.core модулиуд олдохгүй байна.")

STALE_TRACK_FRAMES  = 150
SCORE_DECAY         = 0.98

# Default score weights (auto-learner can override per store)
DEFAULT_WEIGHTS = {
    "looking_around": 1.5,
    "item_pickup": 15.0,
    "body_block": 3.0,
    "crouch": 1.0,
    "wrist_to_torso": 5.0,
    "rapid_movement": 1.5,
}


class ShopliftDetector:
    def __init__(self, device_type: str):
        self.device = device_type
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Half-precision is a GPU feature: PyTorch CPU ops largely lack fp16
        # kernels and silently upcast (or crash). Only enable on CUDA/MPS.
        self.half = device_type in ("cuda", "mps")

        self.pose_model = YOLO("yolo11m-pose.pt").to(self.device)
        self.det_model  = YOLO("yolo11n.pt").to(self.device)

        # Fusing Conv+BN layers is a one-time cost that cuts per-frame latency
        # by ~10-15% with no accuracy impact.
        with contextlib.suppress(Exception):
            self.pose_model.fuse()
            self.det_model.fuse()

        if self.device == "cpu":
            # Single-process multi-camera: give torch all the cores.
            # intra-op threads do the heavy lifting; keep inter-op small so
            # two concurrent model calls don't thrash the scheduler.
            cpu_count = os.cpu_count() or 4
            torch.set_num_threads(max(1, cpu_count - 1))
            with contextlib.suppress(Exception):
                torch.set_num_interop_threads(2)

        self.tracker_history: dict = {}
        self.last_alert_time: dict = {}
        self.frame_count = 0
        self._cached_expensive_items: list = []

    def _get_weights(self, store_id: int) -> dict:
        """Дэлгүүрт тохирсон score weights авах (auto-learned)."""
        config = auto_learner.get_store_config(store_id)
        return config.get("weights", DEFAULT_WEIGHTS)

    def _get_threshold(self, store_id: int, default: float = 80.0) -> float:
        """Дэлгүүрт тохирсон threshold авах (auto-learned)."""
        config = auto_learner.get_store_config(store_id)
        return config.get("threshold", default)

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
            logger.error(f"FFmpeg error: {e}")

    def _async_save_alert(self, yolo_id, frame_to_save, name: str, reason: str,
                          bbox: list, camera_id: int = None, store_id: int = None,
                          score: float = None):
        try:
            from app.services.storage import get_storage

            current_time = int(time.time())
            filename = f"alert_{yolo_id}_{current_time}.jpg"

            try:
                image_url = get_storage().save_image(frame_to_save, filename=filename)
            except Exception as exc:
                logger.error(f"Storage upload failed: {exc} — falling back to local")
                fallback = os.path.join(ALERTS_DIR, filename)
                cv2.imwrite(fallback, frame_to_save)
                image_url = fallback

            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self._save_alert_to_db(
                        person_id=int(yolo_id), image_path=image_url,
                        reason=reason, camera_id=camera_id, store_id=store_id,
                        score=score,
                    )
                )
            finally:
                loop.close()

            try:
                tg_loop = asyncio.new_event_loop()
                tg_loop.run_until_complete(
                    self._send_telegram_alert(
                        store_id=store_id, camera_id=camera_id,
                        reason=reason, image_path=image_url, score=score,
                    )
                )
                tg_loop.close()
            except Exception as tg_err:
                logger.error(f"Telegram notification error: {tg_err}")

            from app.core.state import alert_queue
            alert_queue.put({
                "id": yolo_id,
                "img": image_url, "reason": reason, "name": name,
                "frame": frame_to_save, "bbox": bbox,
                "camera_id": camera_id, "store_id": store_id,
            })
        except Exception as e:
            logger.error(f"Alert save error: {e}")

    async def _send_telegram_alert(self, store_id, camera_id, reason, image_path, score):
        """Дэлгүүрийн telegram_chat_id руу мэдэгдэл илгээх."""
        from app.services.telegram_notifier import telegram_notifier
        if not telegram_notifier.is_configured:
            return

        from app.db.repository.stores import StoreRepository
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            store_repo = StoreRepository(db)
            store = await store_repo.get_by_id(store_id) if store_id else None

        if not store or not store.get("telegram_chat_id"):
            return

        # Камерын нэр авах
        camera_name = f"Camera #{camera_id}" if camera_id else "Unknown"
        cam_state = camera_manager._cameras.get(camera_id)
        if cam_state:
            camera_name = cam_state.name

        await telegram_notifier.send_alert(
            chat_id=store["telegram_chat_id"],
            store_name=store["name"],
            camera_name=camera_name,
            reason=reason,
            image_path=image_path,
            score=score,
        )

    async def _save_alert_to_db(self, person_id, image_path, reason,
                                 camera_id=None, store_id=None, score=None):
        from app.db.repository.alerts import AlertRepository
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            repo = AlertRepository(db)
            await repo.insert_alert(
                person_id=person_id, image_path=image_path, reason=reason,
                camera_id=camera_id, store_id=store_id, confidence_score=score,
            )

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

    def _analyze_behavior(self, curr: dict, kps, person_h: float,
                          expensive_items: list, weights: dict):
        score_delta = 0.0
        reasons = []

        if len(kps) < 17:
            return score_delta, reasons

        l_eye      = kps[1]
        r_eye      = kps[2]
        l_shoulder = kps[5]
        r_shoulder = kps[6]
        l_wrist    = kps[9]
        r_wrist    = kps[10]
        l_hip      = kps[11]
        r_hip      = kps[12]

        shoulder_cx = None
        if self._keypoint_valid(l_shoulder) and self._keypoint_valid(r_shoulder):
            shoulder_cx = (l_shoulder[0] + r_shoulder[0]) / 2

        face_cx = None
        if self._keypoint_valid(l_eye) and self._keypoint_valid(r_eye):
            face_cx = (l_eye[0] + r_eye[0]) / 2

        hip_cy = None
        if self._keypoint_valid(l_hip) and self._keypoint_valid(r_hip):
            hip_cy = (l_hip[1] + r_hip[1]) / 2

        # 1. Looking around
        if face_cx is not None and shoulder_cx is not None:
            offset = abs(face_cx - shoulder_cx)
            if offset > person_h * 0.15:
                score_delta += weights.get("looking_around", 1.5)
                reasons.append("Орчноо харах")

        # 2. Item pickup
        for wrist in [l_wrist, r_wrist]:
            if not self._keypoint_valid(wrist):
                continue
            if not curr["holding"]:
                for item in expensive_items:
                    ix1, iy1, ix2, iy2 = item["box"]
                    if ix1 < wrist[0] < ix2 and iy1 < wrist[1] < iy2:
                        curr["holding"] = item["label"]
                        score_delta += weights.get("item_pickup", 15.0)
                        reasons.append(f"{item['label']} авах")
                        break

        # 3. Body block
        if self._keypoint_valid(l_shoulder) and self._keypoint_valid(r_shoulder):
            shoulder_width = abs(r_shoulder[0] - l_shoulder[0])
            if curr.get("avg_shoulder_w") is None:
                curr["avg_shoulder_w"] = shoulder_width
            else:
                curr["avg_shoulder_w"] = curr["avg_shoulder_w"] * 0.9 + shoulder_width * 0.1
                if shoulder_width < curr["avg_shoulder_w"] * 0.55:
                    score_delta += weights.get("body_block", 3.0)
                    reasons.append("Биеэр далдлах")

        # 4. Crouch
        if hip_cy is not None and shoulder_cx is not None:
            torso_h = abs(hip_cy - l_shoulder[1])
            if torso_h < person_h * 0.15:
                if curr["holding"]:
                    score_delta += 5.0
                    reasons.append("Бөхийж бараа нуух")
                else:
                    score_delta += weights.get("crouch", 1.0)
                    reasons.append("Бөхийх")

        # 5. Wrist to torso
        if curr["holding"] and hip_cy is not None:
            for wrist in [l_wrist, r_wrist]:
                if not self._keypoint_valid(wrist):
                    continue
                wrist_to_hip = abs(wrist[1] - hip_cy)
                if wrist_to_hip < person_h * 0.15:
                    curr["concealment_frames"] += 1
                    if curr["concealment_frames"] % 8 == 0:
                        score_delta += weights.get("wrist_to_torso", 5.0)
                        reasons.append(f"Хувцас доор нуух ({curr['concealment_frames']}f)")
                else:
                    curr["concealment_frames"] = max(0, curr["concealment_frames"] - 1)

        # 6. Rapid movement
        if curr["holding"]:
            for wrist, key in [(l_wrist, "prev_l_wrist"), (r_wrist, "prev_r_wrist")]:
                if not self._keypoint_valid(wrist):
                    continue
                prev = curr.get(key)
                if prev is not None:
                    speed = math.dist(wrist, prev)
                    if speed > person_h * 0.08:
                        score_delta += weights.get("rapid_movement", 1.5)
                        reasons.append("Хурдан хөдөлгөөн")
                curr[key] = tuple(wrist)

        return score_delta, reasons

    def run_inference(self):
        ai_queue = camera_manager.ai_input_queue

        while True:
            try:
                data = ai_queue.get(timeout=2)
                frame = data["frame"]
                full_frame = data.get("full_frame", frame)
                camera_id = data.get("camera_id")
                store_id = data.get("store_id", 0)
                threshold = data.get("threshold", 80.0)
                cooldown = data.get("cooldown", 60)
            except (queue.Empty, TypeError, KeyError):
                continue

            display_frame = full_frame.copy()
            current_time  = time.time()
            self.frame_count += 1

            sh, sw = frame.shape[:2]
            dh, dw = display_frame.shape[:2]
            scale_x = dw / sw if sw else 1.0
            scale_y = dh / sh if sh else 1.0

            # Get per-store weights and threshold (auto-learned)
            weights = self._get_weights(store_id)
            effective_threshold = self._get_threshold(store_id, threshold)

            if self.frame_count % 50 == 0:
                self._cleanup_stale_tracks()

            # inference_mode() disables autograd bookkeeping → lower memory
            # footprint and ~5-10% faster than no_grad on CPU.
            with torch.inference_mode():
                pose_results = self.pose_model.track(
                    frame, persist=True, device=self.device,
                    verbose=False, imgsz=320, half=self.half,
                )

                if self.frame_count % 3 == 0:
                    self._cached_expensive_items = []
                    det_results = self.det_model.predict(
                        frame, conf=0.4, device=self.device,
                        verbose=False, half=self.half,
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
                    bx1, by1, bx2, by2 = boxes[i]
                    person_h = max(1, int(by2 - by1))
                    x1 = int(bx1 * scale_x)
                    y1 = int(by1 * scale_y)
                    x2 = int(bx2 * scale_x)
                    y2 = int(by2 * scale_y)

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
                        curr, keypoints[i], person_h, expensive_items, weights
                    )
                    curr["score"] += delta
                    if reasons:
                        curr["last_reasons"] = reasons

                    if curr["score"] >= effective_threshold:
                        last_alert = self.last_alert_time.get(yolo_id, 0)
                        if current_time - last_alert > cooldown:
                            reason_str = " | ".join(curr["last_reasons"])
                            self.executor.submit(
                                self._async_save_alert,
                                yolo_id, display_frame.copy(),
                                "Unknown", f"🚨 {reason_str}", [x1, y1, x2, y2],
                                camera_id, store_id, curr["score"],
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

            # Update camera manager with display frame
            if camera_id:
                state = camera_manager._cameras.get(camera_id)
                if state:
                    state.latest_frame = display_frame


def ai_inference():
    device = (
        "mps" if torch.backends.mps.is_available()
        else "cuda" if torch.cuda.is_available()
        else "cpu"
    )
    logger.info(f"AI Device: {device}")
    detector = ShopliftDetector(device_type=device)
    detector.run_inference()

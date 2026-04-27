# app/services/ai_service.py

import contextlib
import logging
import math
import os
import queue
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

try:
    import torch
    from ultralytics import YOLO
except ImportError as exc:
    torch = None
    YOLO = None
    _AI_IMPORT_ERROR = exc
else:
    _AI_IMPORT_ERROR = None

logger = logging.getLogger(__name__)

BYTE_TRACK_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "bytetrack.yaml"

try:
    from app.core.config import ALERTS_DIR
    from app.core.geometry import denormalize_polygon, point_in_polygon
    from app.core.severity import (
        DEFAULT_SEVERITY_THRESHOLDS,
        NOTIFY_SEVERITIES,
        SeverityLevel,
        SeverityThresholds,
        classify_severity,
    )
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
        if torch is None or YOLO is None:
            raise RuntimeError(
                "AI dependencies are not installed. Install torch and ultralytics "
                "to run camera inference."
            ) from _AI_IMPORT_ERROR

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

        # Per-camera scoping: one ShopliftDetector multiplexes N cameras onto
        # one YOLO model + one ByteTrack state. Without keying by camera, track
        # IDs collide across cameras and scores leak between unrelated people.
        self.tracker_history: dict = {}  # key: (camera_id, int(yolo_id))
        self._camera_trackers: dict = {}  # key: camera_id -> saved ByteTrack state
        self._active_tracker_camera = None
        self.frame_count = 0
        self._cached_expensive_items: list = []

    def _get_weights(self, store_id: int) -> dict:
        """Дэлгүүрт тохирсон score weights авах (auto-learned)."""
        config = auto_learner.get_store_config(store_id)
        return config.get("weights", DEFAULT_WEIGHTS)

    def _get_threshold(self, store_id: int, default: float = 80.0) -> float:
        """Дэлгүүрт тохирсон threshold авах (auto-learned).

        Kept for backward compatibility with callers that still want a
        single scalar (e.g. UI display). The 4-level classifier in
        `_get_severity_thresholds` is the primary signal now.
        """
        config = auto_learner.get_store_config(store_id)
        return config.get("threshold", default)

    def _get_severity_thresholds(self, store_id: int) -> SeverityThresholds:
        """Resolve the per-store 4-level classifier breakpoints.

        Lookup order:
        1. `auto_learner.get_store_config(store_id)["severity_thresholds"]`
           — a future learner can tune these per store.
        2. Module defaults (40 / 70 / 85 from the T5 spec).

        Never touches the DB from the inference loop; if no cached
        config exists we fall through to defaults rather than block.
        """
        config = auto_learner.get_store_config(store_id)
        raw = config.get("severity_thresholds")
        if isinstance(raw, SeverityThresholds):
            return raw
        if isinstance(raw, dict):
            try:
                return SeverityThresholds(
                    yellow=float(raw["yellow"]),
                    orange=float(raw["orange"]),
                    red=float(raw["red"]),
                )
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "severity_thresholds_invalid_for_store",
                    extra={"store_id": store_id},
                )
        return DEFAULT_SEVERITY_THRESHOLDS

    @staticmethod
    def _get_tracker_config_path() -> str:
        if not BYTE_TRACK_CONFIG_PATH.exists():
            raise FileNotFoundError(f"ByteTrack config not found: {BYTE_TRACK_CONFIG_PATH}")
        return str(BYTE_TRACK_CONFIG_PATH)

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
                          score: float = None, cooldown_seconds: int = 60,
                          severity: SeverityLevel = "yellow"):
        import asyncio

        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self._dispatch_alert(
                        yolo_id=yolo_id,
                        frame_to_save=frame_to_save,
                        name=name,
                        reason=reason,
                        bbox=bbox,
                        camera_id=camera_id,
                        store_id=store_id,
                        score=score,
                        cooldown_seconds=cooldown_seconds,
                        severity=severity,
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Alert save error: {e}")

    async def _dispatch_alert(self, *, yolo_id, frame_to_save, name, reason,
                              bbox, camera_id, store_id, score, cooldown_seconds,
                              severity: SeverityLevel = "yellow"):
        """Single-session orchestration: dedup → persist → record → notify.

        Routes every step through AlertManager so that Telegram is only
        notified after the alert is both approved by dedup and persisted.
        Always called from the AI inference thread (never from a
        request handler) — runs under `system_bypass` so the alert
        insert, dedup lookup, and store fetch succeed regardless of
        whether RLS is enforced.
        """
        from datetime import UTC, datetime, timedelta

        from app.core.tenancy_context import system_bypass
        from app.db.session import AsyncSessionLocal
        from app.services.alert_manager import alert_manager
        from app.services.storage import get_storage

        person_track_id = int(yolo_id)
        cooldown = max(0, int(cooldown_seconds or 0))

        with system_bypass():
            async with AsyncSessionLocal() as db:
                decision = await alert_manager.should_send_alert(
                    db,
                    camera_id=camera_id,
                    person_track_id=person_track_id,
                    cooldown_seconds=cooldown,
                )
                if not decision.should_alert:
                    logger.info(
                        "Alert suppressed for camera_id=%s person_track_id=%s: %s",
                        camera_id,
                        person_track_id,
                        decision.reason,
                    )
                    return

                filename = f"alert_{yolo_id}_{int(time.time())}.jpg"
                try:
                    image_url = get_storage().save_image(frame_to_save, filename=filename)
                except Exception as exc:
                    logger.error(f"Storage upload failed: {exc} — falling back to local")
                    fallback = os.path.join(ALERTS_DIR, filename)
                    cv2.imwrite(fallback, frame_to_save)
                    image_url = fallback

                # --- RAG + VLM verification ---------------------------------
                # Runs *after* the cooldown gate so we don't waste GPU
                # cycles on duplicates, and *before* the alert insert so
                # the verdict columns are populated atomically with the
                # row. Failures inside the pipeline downgrade to
                # "not_run" — see rag_vlm_pipeline.evaluate.
                from app.db.repository.stores import StoreRepository
                from app.schemas.store_settings import resolve_settings
                from app.services import rag_vlm_pipeline

                store_settings = None
                if store_id is not None:
                    store_row = await StoreRepository(db).get_by_id(store_id)
                    if store_row:
                        store_settings = resolve_settings(store_row.get("settings"))

                pipeline_decision = await rag_vlm_pipeline.evaluate(
                    description=reason,
                    frame=frame_to_save,
                    store_id=store_id,
                    store_settings=store_settings,
                    db=db,
                )

                from app.db.repository.alerts import AlertRepository

                alert_id = await AlertRepository(db).insert_alert(
                    person_id=person_track_id,
                    image_path=image_url,
                    reason=reason,
                    camera_id=camera_id,
                    store_id=store_id,
                    confidence_score=score,
                    severity=severity,
                    person_track_id=person_track_id,
                    rag_decision=pipeline_decision.rag_decision,
                    vlm_decision=pipeline_decision.vlm_decision,
                    suppressed=pipeline_decision.suppressed,
                    suppressed_reason=pipeline_decision.suppressed_reason,
                )
                if alert_id is None:
                    logger.warning(
                        "Alert insert returned None after dedup approved; "
                        "camera_id=%s person_track_id=%s",
                        camera_id,
                        person_track_id,
                    )
                    return

                now = datetime.now(UTC)
                await alert_manager.record_alert_committed(
                    db,
                    camera_id=camera_id,
                    person_track_id=person_track_id,
                    alert_id=alert_id,
                    now=now,
                    cooldown_until=now + timedelta(seconds=cooldown),
                )

                # Persist the VLM caption (if any) so the frontend can
                # render it next to the alert. Done inside the same DB
                # session so we don't open a second connection just to
                # write one row.
                if pipeline_decision.vlm_verdict is not None:
                    try:
                        await rag_vlm_pipeline.persist_vlm_annotation(
                            db=db,
                            alert_id=alert_id,
                            verdict=pipeline_decision.vlm_verdict,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to persist VLM annotation for alert_id=%s",
                            alert_id,
                        )

            # Suppressed alerts stay in the DB (so dashboards can chart
            # suppression rate) but never fire downstream notifications.
            if pipeline_decision.suppressed:
                logger.info(
                    "Alert %s suppressed by %s: %s",
                    alert_id,
                    pipeline_decision.rag_decision
                    if pipeline_decision.rag_decision == "suppressed_by_rag"
                    else pipeline_decision.vlm_decision,
                    pipeline_decision.suppressed_reason,
                )
                return

            try:
                # T5-06/07/08/09 — fan out across every configured
                # channel + log each delivery to `alert_escalations`.
                # The dispatcher swallows per-channel failures so we
                # wrap broadly only to catch import/bootstrap issues.
                from app.services.escalation_dispatcher import (
                    AlertContext,
                    dispatch_alert,
                )

                await dispatch_alert(
                    AlertContext(
                        alert_id=alert_id,
                        store_id=store_id,
                        camera_id=camera_id,
                        severity=severity,
                        reason=reason,
                        image_path=image_url,
                        score=score,
                    )
                )
            except Exception as tg_err:
                logger.error(f"Alert escalation error: {tg_err}")

            from app.core.state import alert_queue
            alert_queue.put({
                "id": yolo_id,
                "img": image_url, "reason": reason, "name": name,
                "frame": frame_to_save, "bbox": bbox,
                "camera_id": camera_id, "store_id": store_id,
            })

    async def _send_telegram_alert(self, store_id, camera_id, reason, image_path, score,
                                   severity: SeverityLevel = "yellow",
                                   alert_id: int | None = None):
        """Дэлгүүрийн Telegram subscribers руу мэдэгдэл илгээх.

        T5-04 fan-out: if `store_telegram_subscribers` rows exist for the
        store, every subscriber gets the alert. Falls back to the legacy
        `stores.telegram_chat_id` singleton when no subscriber rows exist
        so existing deployments keep working without a migration.
        """
        from app.services.telegram_notifier import telegram_notifier
        if not telegram_notifier.is_configured:
            return

        from app.db.repository.stores import StoreRepository
        from app.db.repository.telegram_subscribers import (
            TelegramSubscriberRepository,
        )
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            store_repo = StoreRepository(db)
            store = await store_repo.get_by_id(store_id) if store_id else None
            if not store:
                return
            subscriber_rows = (
                await TelegramSubscriberRepository(db).list_for_store(store_id)
                if store_id else []
            )

        chat_ids: list[str] = [row["chat_id"] for row in subscriber_rows]
        if not chat_ids and store.get("telegram_chat_id"):
            chat_ids = [store["telegram_chat_id"]]
        if not chat_ids:
            return

        camera_name = f"Camera #{camera_id}" if camera_id else "Unknown"
        cam_state = camera_manager._cameras.get(camera_id)
        if cam_state:
            camera_name = cam_state.name

        for chat_id in chat_ids:
            try:
                await telegram_notifier.send_alert(
                    chat_id=chat_id,
                    store_name=store["name"],
                    camera_name=camera_name,
                    reason=reason,
                    image_path=image_path,
                    score=score,
                    severity=severity,
                    alert_id=alert_id,
                )
            except Exception as per_chat_err:
                # One bad chat_id (user blocked the bot, invalid id, etc.)
                # must not prevent the rest of the fan-out.
                logger.error(
                    "telegram_alert_send_failed",
                    extra={"chat_id": chat_id, "error": str(per_chat_err)},
                )

    @staticmethod
    def _keypoint_valid(kp) -> bool:
        return kp[0] > 1.0 and kp[1] > 1.0

    def _cleanup_stale_tracks(self):
        stale_keys = [
            key for key, data in self.tracker_history.items()
            if self.frame_count - data["last_seen"] > STALE_TRACK_FRAMES
        ]
        for key in stale_keys:
            del self.tracker_history[key]

    def _swap_to_camera_tracker(self, camera_id):
        """Swap Ultralytics' ByteTrack state to the current camera's state.

        Without this, frames from different cameras hit the same predictor and
        ByteTrack matches bboxes across cameras as if they were one stream,
        corrupting track identity even when dict keys are camera-scoped.
        """
        if camera_id is None or self._active_tracker_camera == camera_id:
            return

        predictor = getattr(self.pose_model, "predictor", None)
        if predictor is not None:
            if self._active_tracker_camera is not None:
                current = getattr(predictor, "trackers", None)
                if current is not None:
                    self._camera_trackers[self._active_tracker_camera] = current

            if camera_id in self._camera_trackers:
                predictor.trackers = self._camera_trackers[camera_id]
            elif hasattr(predictor, "trackers"):
                delattr(predictor, "trackers")

        self._active_tracker_camera = camera_id

    def _analyze_behavior(self, curr: dict, kps, person_h: float,
                          expensive_items: list, weights: dict,
                          shelf_zones_px: list | None = None):
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

        # 2. Item pickup / shelf interaction
        # Shelf ROI zones are the primary signal because they work for any
        # retail category (grocery, apparel, cosmetics) — COCO's 80-class
        # model only catches bottle/cell phone/handbag/laptop. Zones win
        # when configured; COCO is the zero-config fallback.
        for wrist in [l_wrist, r_wrist]:
            if not self._keypoint_valid(wrist):
                continue
            if curr["holding"]:
                continue

            matched_label = None
            if shelf_zones_px:
                for zone in shelf_zones_px:
                    if point_in_polygon(wrist, zone["polygon"]):
                        matched_label = zone["name"]
                        break
            else:
                for item in expensive_items:
                    ix1, iy1, ix2, iy2 = item["box"]
                    if ix1 < wrist[0] < ix2 and iy1 < wrist[1] < iy2:
                        matched_label = item["label"]
                        break

            if matched_label:
                curr["holding"] = matched_label
                score_delta += weights.get("item_pickup", 15.0)
                reasons.append(f"{matched_label} авах")
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
                shelf_zones = data.get("shelf_zones") or []
            except (queue.Empty, TypeError, KeyError):
                continue

            display_frame = full_frame.copy()
            self.frame_count += 1

            sh, sw = frame.shape[:2]
            dh, dw = display_frame.shape[:2]
            scale_x = dw / sw if sw else 1.0
            scale_y = dh / sh if sh else 1.0

            # Get per-store weights + severity thresholds (auto-learned).
            # `threshold` from the queue is kept for legacy display paths
            # but the 4-level classifier below decides when to alert.
            weights = self._get_weights(store_id)
            severity_thresholds = self._get_severity_thresholds(store_id)

            if self.frame_count % 50 == 0:
                self._cleanup_stale_tracks()

            self._swap_to_camera_tracker(camera_id)

            # inference_mode() disables autograd bookkeeping → lower memory
            # footprint and ~5-10% faster than no_grad on CPU.
            with torch.inference_mode():
                pose_results = self.pose_model.track(
                    frame, persist=True, device=self.device,
                    verbose=False, imgsz=320, half=self.half,
                    tracker=self._get_tracker_config_path(),
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

            # Precompute pixel-space shelf polygons once per frame — wrist
            # keypoints live in `frame` coords, not `full_frame`, because
            # pose_model ran against the resized frame.
            shelf_zones_px: list[dict] = []
            if shelf_zones:
                for z in shelf_zones:
                    poly = z.get("polygon") or []
                    if len(poly) < 3:
                        continue
                    shelf_zones_px.append({
                        "name": z.get("name") or "shelf",
                        "polygon": denormalize_polygon(poly, sw, sh),
                    })

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

                    track_key = (camera_id, int(yolo_id))
                    if track_key not in self.tracker_history:
                        self.tracker_history[track_key] = {
                            "holding": None,
                            "score": 0.0,
                            "last_seen": self.frame_count,
                            "concealment_frames": 0,
                            "avg_shoulder_w": None,
                            "prev_l_wrist": None,
                            "prev_r_wrist": None,
                            "last_reasons": [],
                        }

                    curr = self.tracker_history[track_key]
                    curr["last_seen"] = self.frame_count

                    if not curr["holding"]:
                        curr["score"] = max(0.0, curr["score"] * SCORE_DECAY)
                    else:
                        curr["score"] = max(0.0, curr["score"] * 0.999)

                    delta, reasons = self._analyze_behavior(
                        curr, keypoints[i], person_h, expensive_items, weights,
                        shelf_zones_px,
                    )
                    curr["score"] += delta
                    if reasons:
                        curr["last_reasons"] = reasons

                    severity = classify_severity(curr["score"], severity_thresholds)

                    if severity in NOTIFY_SEVERITIES:
                        reason_str = " | ".join(curr["last_reasons"])
                        self.executor.submit(
                            self._async_save_alert,
                            yolo_id, display_frame.copy(),
                            "Unknown", f"🚨 {reason_str}", [x1, y1, x2, y2],
                            camera_id, store_id, curr["score"], cooldown,
                            severity,
                        )
                        curr["score"] = 0.0
                        curr["holding"] = None
                        curr["concealment_frames"] = 0
                        curr["last_reasons"] = []

                    # Bounding-box color reflects the classifier tier so the
                    # review dashboard and the raw stream agree on severity.
                    # BGR tuples for OpenCV (not RGB).
                    if severity == "red":
                        border_color, status_text = (0, 0, 255), "THEFT DETECTED"
                    elif severity == "orange":
                        border_color, status_text = (0, 128, 255), "SUSPICIOUS"
                    elif severity == "yellow":
                        border_color, status_text = (0, 215, 255), "WATCH"
                    else:
                        border_color, status_text = (0, 255, 0), "NORMAL"

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
    if torch is None:
        logger.warning(
            "AI inference disabled because torch/ultralytics dependencies "
            "are not installed",
            exc_info=_AI_IMPORT_ERROR,
        )
        return

    device = (
        "mps" if torch.backends.mps.is_available()
        else "cuda" if torch.cuda.is_available()
        else "cpu"
    )
    logger.info(f"AI Device: {device}")
    detector = ShopliftDetector(device_type=device)
    detector.run_inference()

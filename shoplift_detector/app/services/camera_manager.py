"""Dynamic camera manager - олон дэлгүүр, олон камерыг удирдах.
Runtime-д камер нэмэх/хасах боломжтой, restart шаарддаггүй."""

import contextlib
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import cv2
from app.core.config import settings

logger = logging.getLogger(__name__)


def _resolve_source(url: str, camera_type: str):
    """Return an opencv-compatible source or None if unusable on this host.

    USB/integer sources are validated against /dev/videoN so headless
    servers (Railway, Docker without --device) don't enter an infinite
    reconnect loop trying to open a camera that can never exist.
    """
    override = os.getenv("CAMERA_SOURCE") or settings.CAMERA_SOURCE
    if override:
        url = override

    if camera_type == "usb":
        try:
            idx = int(url)
        except (TypeError, ValueError):
            return None
        if idx < 0:
            return None
        device_path = f"/dev/video{idx}"
        if not os.path.exists(device_path):
            logger.warning(
                "Skipping USB camera index %s — %s not present on host",
                idx, device_path,
            )
            return None
        return idx

    if not url:
        return None
    return url


@dataclass
class CameraState:
    camera_id: int
    store_id: int
    name: str
    url: str
    camera_type: str
    is_ai_enabled: bool
    alert_threshold: float = 80.0
    alert_cooldown: int = 15
    # Runtime state
    thread: threading.Thread | None = None
    latest_frame: object | None = None  # numpy array
    is_connected: bool = False
    fps: float = 0.0
    last_frame_at: datetime | None = None
    _stop_event: threading.Event = field(default_factory=threading.Event)


class CameraManager:
    """Бүх камерыг динамикаар удирдах singleton."""

    def __init__(self):
        self._cameras: dict[int, CameraState] = {}
        self._lock = threading.Lock()
        self.ai_input_queue: queue.Queue = queue.Queue(
            maxsize=settings.AI_QUEUE_MAXSIZE
        )

    def register_camera(self, camera_id: int, store_id: int, name: str,
                        url: str, camera_type: str, is_ai_enabled: bool = True,
                        alert_threshold: float = 80.0, alert_cooldown: int = 15):
        with self._lock:
            if camera_id in self._cameras:
                self.unregister_camera(camera_id)

            state = CameraState(
                camera_id=camera_id, store_id=store_id, name=name,
                url=url, camera_type=camera_type, is_ai_enabled=is_ai_enabled,
                alert_threshold=alert_threshold, alert_cooldown=alert_cooldown,
            )
            self._cameras[camera_id] = state
            self._start_capture(state)
            logger.info(f"Camera registered: {name} (id={camera_id}, store={store_id})")

    def unregister_camera(self, camera_id: int):
        with self._lock:
            state = self._cameras.pop(camera_id, None)
            if state:
                state._stop_event.set()
                logger.info(f"Camera unregistered: {state.name} (id={camera_id})")

    def _start_capture(self, state: CameraState):
        thread = threading.Thread(
            target=self._capture_loop,
            args=(state,),
            daemon=True,
            name=f"cam-{state.camera_id}-{state.name}",
        )
        state.thread = thread
        thread.start()

    def _open_capture(self, state: CameraState, source):
        cap = cv2.VideoCapture(source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _enqueue_ai_frame(self, payload: dict):
        """Bounded queue with drop-oldest semantics — newest frames win
        so the AI worker never processes stale data during bursts."""
        try:
            self.ai_input_queue.put_nowait(payload)
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self.ai_input_queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self.ai_input_queue.put_nowait(payload)

    def _capture_loop(self, state: CameraState):
        source = _resolve_source(state.url, state.camera_type)
        if source is None:
            logger.warning(
                f"[{state.name}] No usable video source on this host — "
                f"camera will stay offline"
            )
            state.is_connected = False
            return

        logger.info(f"[{state.name}] Connecting to {source}")
        cap = self._open_capture(state, source)
        backoff = settings.RTSP_RECONNECT_BASE
        max_backoff = settings.RTSP_RECONNECT_MAX
        skip_n = max(1, settings.AI_FRAME_SKIP)
        target = max(64, settings.AI_INPUT_SIZE)

        frame_count = 0
        ai_counter = 0
        fps_start = time.time()
        state.is_connected = cap.isOpened()
        if state.is_connected:
            logger.info(f"[{state.name}] Connected successfully")

        try:
            while not state._stop_event.is_set():
                if not state.is_connected:
                    logger.warning(
                        f"[{state.name}] Reconnecting in {backoff:.1f}s"
                    )
                    if state._stop_event.wait(backoff):
                        break
                    backoff = min(backoff * 2, max_backoff)
                    cap.release()
                    cap = self._open_capture(state, source)
                    if cap.isOpened():
                        state.is_connected = True
                        backoff = settings.RTSP_RECONNECT_BASE
                        logger.info(f"[{state.name}] Reconnected")
                    continue

                success, frame = cap.read()
                if not success:
                    state.is_connected = False
                    continue

                state.latest_frame = frame
                state.last_frame_at = datetime.now()
                frame_count += 1

                elapsed = time.time() - fps_start
                if elapsed >= 5.0:
                    state.fps = round(frame_count / elapsed, 1)
                    frame_count = 0
                    fps_start = time.time()

                ai_counter += 1
                if state.is_ai_enabled and ai_counter % skip_n == 0:
                    h, w = frame.shape[:2]
                    scale = target / max(h, w)
                    small = (
                        cv2.resize(frame, (int(w * scale), int(h * scale)))
                        if scale < 1.0
                        else frame
                    )
                    self._enqueue_ai_frame({
                        "frame": small,
                        "full_frame": frame,
                        "camera_id": state.camera_id,
                        "store_id": state.store_id,
                        "source": state.name,
                        "threshold": state.alert_threshold,
                        "cooldown": state.alert_cooldown,
                    })

                time.sleep(0.01)
        except Exception as e:
            logger.error(f"[{state.name}] Error: {e}")
        finally:
            cap.release()
            state.is_connected = False

    def get_frame(self, camera_id: int) -> object | None:
        state = self._cameras.get(camera_id)
        if state and state.latest_frame is not None:
            return state.latest_frame.copy()
        return None

    def get_store_frames(self, store_id: int) -> list:
        frames = []
        with self._lock:
            for state in self._cameras.values():
                if state.store_id == store_id and state.latest_frame is not None:
                    frames.append(state.latest_frame.copy())
        return frames

    def get_all_status(self) -> list[dict]:
        statuses = []
        with self._lock:
            for cam_id, state in self._cameras.items():
                statuses.append({
                    "camera_id": cam_id,
                    "name": state.name,
                    "store_id": state.store_id,
                    "is_connected": state.is_connected,
                    "fps": state.fps,
                    "last_frame_at": state.last_frame_at.isoformat() if state.last_frame_at else None,
                    "is_ai_enabled": state.is_ai_enabled,
                })
        return statuses

    def get_camera_count(self) -> int:
        return len(self._cameras)

    def get_connected_count(self) -> int:
        return sum(1 for s in self._cameras.values() if s.is_connected)


# Global singleton
camera_manager = CameraManager()

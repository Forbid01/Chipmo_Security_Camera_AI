"""Dynamic camera manager - олон дэлгүүр, олон камерыг удирдах.
Runtime-д камер нэмэх/хасах боломжтой, restart шаарддаггүй."""

import cv2
import time
import queue
import logging
import threading
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


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
    thread: Optional[threading.Thread] = None
    latest_frame: Optional[object] = None  # numpy array
    is_connected: bool = False
    fps: float = 0.0
    last_frame_at: Optional[datetime] = None
    _stop_event: threading.Event = field(default_factory=threading.Event)


class CameraManager:
    """Бүх камерыг динамикаар удирдах singleton."""

    def __init__(self):
        self._cameras: Dict[int, CameraState] = {}
        self._lock = threading.Lock()
        self.ai_input_queue = queue.Queue(maxsize=8)

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

    def _capture_loop(self, state: CameraState):
        source = state.url
        if state.camera_type == "usb":
            try:
                source = int(source)
            except ValueError:
                pass

        logger.info(f"[{state.name}] Connecting to {source}")
        cap = cv2.VideoCapture(source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            logger.error(f"[{state.name}] Connection failed")
            state.is_connected = False
            return

        state.is_connected = True
        logger.info(f"[{state.name}] Connected successfully")
        frame_count = 0
        fps_start = time.time()

        try:
            while not state._stop_event.is_set():
                success, frame = cap.read()
                if not success:
                    state.is_connected = False
                    logger.warning(f"[{state.name}] Disconnected, reconnecting...")
                    time.sleep(2)
                    cap.release()
                    cap = cv2.VideoCapture(source)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if cap.isOpened():
                        state.is_connected = True
                    continue

                state.latest_frame = frame.copy()
                state.last_frame_at = datetime.now()
                frame_count += 1

                # FPS calculation
                elapsed = time.time() - fps_start
                if elapsed >= 5.0:
                    state.fps = round(frame_count / elapsed, 1)
                    frame_count = 0
                    fps_start = time.time()

                # AI queue
                if state.is_ai_enabled and not self.ai_input_queue.full():
                    try:
                        self.ai_input_queue.put_nowait({
                            "frame": frame.copy(),
                            "camera_id": state.camera_id,
                            "store_id": state.store_id,
                            "source": state.name,
                            "threshold": state.alert_threshold,
                            "cooldown": state.alert_cooldown,
                        })
                    except queue.Full:
                        pass

                time.sleep(0.02)
        except Exception as e:
            logger.error(f"[{state.name}] Error: {e}")
        finally:
            cap.release()
            state.is_connected = False

    def get_frame(self, camera_id: int) -> Optional[object]:
        state = self._cameras.get(camera_id)
        if state and state.latest_frame is not None:
            return state.latest_frame.copy()
        return None

    def get_store_frames(self, store_id: int) -> List:
        frames = []
        with self._lock:
            for state in self._cameras.values():
                if state.store_id == store_id and state.latest_frame is not None:
                    frames.append(state.latest_frame.copy())
        return frames

    def get_all_status(self) -> List[dict]:
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

"""Dynamic camera manager - олон дэлгүүр, олон камерыг удирдах.
Runtime-д камер нэмэх/хасах боломжтой, restart шаарддаггүй."""

import asyncio
import contextlib
import logging
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

import cv2
from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RTSP_RECONNECT_SECONDS = 60.0


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
    # Runtime state. `frame_buffer` is a 1-slot deque so an appendleft()
    # by the capture thread atomically drops the previous (stale) frame —
    # readers always see the newest frame, never a torn write.
    thread: threading.Thread | None = None
    frame_buffer: deque = field(default_factory=lambda: deque(maxlen=1))
    frame_condition: threading.Condition = field(default_factory=threading.Condition)
    is_connected: bool = False
    fps: float = 0.0
    last_frame_at: datetime | None = None
    last_error: str | None = None
    offline_since_monotonic: float | None = None
    last_health_report_monotonic: float = 0.0
    last_offline_notification_monotonic: float = 0.0
    _stop_event: threading.Event = field(default_factory=threading.Event)

    @property
    def latest_frame(self):
        # Back-compat shim for ai_service which assigns to this attribute
        # after annotating a frame. Reading returns the newest buffered frame.
        return self.frame_buffer[0] if self.frame_buffer else None

    @latest_frame.setter
    def latest_frame(self, frame):
        self.frame_buffer.append(frame)
        with self.frame_condition:
            self.frame_condition.notify_all()


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

    @staticmethod
    def _reconnect_base_backoff() -> float:
        return max(0.1, float(settings.RTSP_RECONNECT_BASE))

    @staticmethod
    def _reconnect_max_backoff() -> float:
        return min(float(settings.RTSP_RECONNECT_MAX), MAX_RTSP_RECONNECT_SECONDS)

    @staticmethod
    def _next_reconnect_backoff(current: float, max_backoff: float) -> float:
        return min(current * 2, max_backoff, MAX_RTSP_RECONNECT_SECONDS)

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

    def _mark_online(self, state: CameraState):
        state.is_connected = True
        state.last_error = None
        state.offline_since_monotonic = None

    def _mark_offline(self, state: CameraState, error: str | None = None):
        state.is_connected = False
        state.last_error = error
        if state.offline_since_monotonic is None:
            state.offline_since_monotonic = time.monotonic()

    def _should_report_health(self, state: CameraState, *, force: bool = False) -> bool:
        if force:
            return True
        elapsed = time.monotonic() - state.last_health_report_monotonic
        return elapsed >= settings.CAMERA_HEALTH_HEARTBEAT_INTERVAL_SECONDS

    def _report_camera_health(self, state: CameraState, *, force: bool = False):
        if not self._should_report_health(state, force=force):
            return

        state.last_health_report_monotonic = time.monotonic()
        status = self._get_health_status(state)

        async def _write_health():
            from app.db.repository.camera_health import CameraHealthRepository
            from app.db.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                repo = CameraHealthRepository(db)
                await repo.upsert_heartbeat(
                    camera_id=state.camera_id,
                    store_id=state.store_id,
                    status=status,
                    is_connected=state.is_connected,
                    fps=state.fps,
                    last_frame_at=state.last_frame_at,
                    last_error=state.last_error,
                    now=datetime.now(UTC),
                )

        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_write_health())
            finally:
                loop.close()
        except Exception as exc:
            logger.warning(
                "[%s] Camera health heartbeat failed: %s",
                state.name,
                exc,
            )

    def _maybe_notify_offline(self, state: CameraState):
        if self._get_health_status(state) != "offline" or state.offline_since_monotonic is None:
            return

        now = time.monotonic()
        offline_for = now - state.offline_since_monotonic
        notify_after = settings.CAMERA_HEALTH_NOTIFICATION_AFTER_SECONDS
        if offline_for < notify_after:
            return

        if now - state.last_offline_notification_monotonic < notify_after:
            return

        state.last_offline_notification_monotonic = now
        logger.warning(
            "[%s] Camera offline for %.0fs; notification hook triggered",
            state.name,
            offline_for,
        )

        async def _mark_notification():
            from app.db.repository.camera_health import CameraHealthRepository
            from app.db.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                await CameraHealthRepository(db).mark_notification_sent(
                    camera_id=state.camera_id,
                    notified_at=datetime.now(UTC),
                )

        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_mark_notification())
            finally:
                loop.close()
        except Exception as exc:
            logger.warning(
                "[%s] Camera offline notification marker failed: %s",
                state.name,
                exc,
            )

    def _get_health_status(self, state: CameraState) -> str:
        if state.is_connected:
            return "online"
        if state.offline_since_monotonic is None:
            return "offline"
        offline_for = time.monotonic() - state.offline_since_monotonic
        if offline_for < settings.CAMERA_HEALTH_OFFLINE_AFTER_SECONDS:
            return "degraded"
        return "offline"

    def _capture_loop(self, state: CameraState):
        source = _resolve_source(state.url, state.camera_type)
        if source is None:
            logger.warning(
                f"[{state.name}] No usable video source on this host — "
                f"camera will stay offline"
            )
            self._mark_offline(state, "no_usable_video_source")
            self._report_camera_health(state, force=True)
            return

        logger.info(f"[{state.name}] Connecting to {source}")
        cap = self._open_capture(state, source)
        backoff = self._reconnect_base_backoff()
        max_backoff = self._reconnect_max_backoff()
        skip_n = max(1, settings.AI_FRAME_SKIP)
        target = max(64, settings.AI_INPUT_SIZE)

        frame_count = 0
        ai_counter = 0
        fps_start = time.time()
        if cap.isOpened():
            self._mark_online(state)
        else:
            self._mark_offline(state, "capture_open_failed")
        if state.is_connected:
            logger.info(f"[{state.name}] Connected successfully")
        self._report_camera_health(state, force=True)

        try:
            while not state._stop_event.is_set():
                if not state.is_connected:
                    self._report_camera_health(state)
                    self._maybe_notify_offline(state)
                    logger.warning(
                        f"[{state.name}] Reconnecting in {backoff:.1f}s"
                    )
                    if state._stop_event.wait(backoff):
                        break
                    backoff = self._next_reconnect_backoff(backoff, max_backoff)
                    cap.release()
                    cap = self._open_capture(state, source)
                    if cap.isOpened():
                        self._mark_online(state)
                        backoff = self._reconnect_base_backoff()
                        logger.info(f"[{state.name}] Reconnected")
                        self._report_camera_health(state, force=True)
                    continue

                success, frame = cap.read()
                if not success:
                    self._mark_offline(state, "frame_read_failed")
                    self._report_camera_health(state)
                    continue

                self._mark_online(state)
                # deque(maxlen=1).append() drops any unconsumed prior frame,
                # so memory stays bounded even if readers fall behind.
                state.frame_buffer.append(frame)
                with state.frame_condition:
                    state.frame_condition.notify_all()
                state.last_frame_at = datetime.now(UTC)
                frame_count += 1

                elapsed = time.time() - fps_start
                if elapsed >= 5.0:
                    state.fps = round(frame_count / elapsed, 1)
                    frame_count = 0
                    fps_start = time.time()

                self._report_camera_health(state)

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
            self._mark_offline(state, str(e))
            self._report_camera_health(state, force=True)
        finally:
            cap.release()
            self._mark_offline(state, "capture_loop_stopped")
            self._report_camera_health(state, force=True)

    def get_frame(self, camera_id: int) -> object | None:
        state = self._cameras.get(camera_id)
        if not state:
            return None
        frame = state.latest_frame
        return frame.copy() if frame is not None else None

    def has_camera(self, camera_id: int) -> bool:
        return camera_id in self._cameras

    def wait_for_frame(self, camera_id: int, timeout: float = 1.0):
        """Block until a new frame is available — lets consumers idle without
        burning CPU on polling loops. Returns the frame or None on timeout."""
        state = self._cameras.get(camera_id)
        if not state:
            return None
        with state.frame_condition:
            state.frame_condition.wait(timeout=timeout)
        return self.get_frame(camera_id)

    def get_store_frames(self, store_id: int) -> list:
        frames = []
        with self._lock:
            for state in self._cameras.values():
                if state.store_id == store_id:
                    frame = state.latest_frame
                    if frame is not None:
                        frames.append(frame.copy())
        return frames

    def shutdown_all(self):
        """Graceful stop — signals every capture thread, releases VideoCapture
        handles, and destroys any OpenCV windows. Call from lifespan shutdown
        so Railway doesn't leave ghost ffmpeg processes on redeploy."""
        with self._lock:
            states = list(self._cameras.values())
            self._cameras.clear()

        for state in states:
            state._stop_event.set()
            with state.frame_condition:
                state.frame_condition.notify_all()

        for state in states:
            if state.thread and state.thread.is_alive():
                state.thread.join(timeout=2.0)

        with contextlib.suppress(Exception):
            cv2.destroyAllWindows()
        logger.info("camera_manager_shutdown_complete")

    def get_all_status(self) -> list[dict]:
        statuses = []
        with self._lock:
            for cam_id, state in self._cameras.items():
                statuses.append({
                    "camera_id": cam_id,
                    "name": state.name,
                    "store_id": state.store_id,
                    "is_connected": state.is_connected,
                    "health_status": self._get_health_status(state),
                    "fps": state.fps,
                    "last_frame_at": state.last_frame_at.isoformat() if state.last_frame_at else None,
                    "last_error": state.last_error,
                    "is_ai_enabled": state.is_ai_enabled,
                })
        return statuses

    def get_camera_count(self) -> int:
        return len(self._cameras)

    def get_connected_count(self) -> int:
        return sum(1 for s in self._cameras.values() if s.is_connected)


# Global singleton
camera_manager = CameraManager()

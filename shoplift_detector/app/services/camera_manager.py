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
    # Shelf ROI polygons (normalized 0..1 coords) passed per-frame to the AI
    # service so the detector can score "hand enters shelf" interactions
    # independently of COCO object classes. Empty = fall back to legacy.
    shelf_zones: list = field(default_factory=list)
    # Optional secondary (sub-stream) RTSP URL for AI inference.
    # When set: primary stream feeds display only; sub-stream feeds AI.
    # When unset: primary stream feeds both display and AI (legacy behavior).
    substream_url: str | None = None
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
    # Sub-stream runtime state (only used when substream_url is set)
    _substream_thread: threading.Thread | None = None
    _substream_stop_event: threading.Event = field(default_factory=threading.Event)
    _substream_connected: bool = False

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
        # Bound to the FastAPI lifespan loop so capture threads can submit
        # async DB work without spinning up a throwaway loop per heartbeat —
        # AsyncSessionLocal/engine are bound to one loop, and a fresh loop
        # crashes asyncpg with "Future attached to a different loop" during
        # connection pool teardown.
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def attach_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Pin the main event loop. Call from the FastAPI lifespan before
        registering cameras so the first health heartbeat has somewhere
        to land."""
        self._main_loop = loop

    def detach_event_loop(self) -> None:
        """Drop the loop reference so threads stop submitting to a loop
        that's about to close. Call from lifespan shutdown before the
        event loop tears down."""
        self._main_loop = None

    def _submit_async(self, coro, *, op: str, camera_name: str) -> None:
        """Schedule a coroutine on the main event loop without blocking
        the capture thread. Never waits on the future — DB I/O must not
        stall frame capture — but attaches a done callback so exceptions
        aren't silently swallowed.

        If no loop is attached (pre-lifespan or post-shutdown) the
        coroutine is closed to avoid a "coroutine was never awaited"
        warning and the submission is skipped.
        """
        loop = self._main_loop
        if loop is None or loop.is_closed():
            coro.close()
            return
        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            # Loop closed between the check and submit — rare race during
            # shutdown. Close the coroutine and move on.
            coro.close()
            return

        def _on_done(fut):
            exc = fut.exception()
            if exc is not None:
                logger.warning("[%s] %s failed: %s", camera_name, op, exc)

        future.add_done_callback(_on_done)

    def register_camera(self, camera_id: int, store_id: int, name: str,
                        url: str, camera_type: str, is_ai_enabled: bool = True,
                        alert_threshold: float = 80.0, alert_cooldown: int = 15,
                        shelf_zones: list | None = None,
                        substream_url: str | None = None):
        with self._lock:
            if camera_id in self._cameras:
                self.unregister_camera(camera_id)

            state = CameraState(
                camera_id=camera_id, store_id=store_id, name=name,
                url=url, camera_type=camera_type, is_ai_enabled=is_ai_enabled,
                alert_threshold=alert_threshold, alert_cooldown=alert_cooldown,
                shelf_zones=list(shelf_zones) if shelf_zones else [],
                substream_url=substream_url or None,
            )
            self._cameras[camera_id] = state
            self._start_capture(state)
            if state.substream_url:
                self._start_substream_capture(state)
            logger.info(
                f"Camera registered: {name} (id={camera_id}, store={store_id}"
                + (f", substream=yes" if state.substream_url else "")
                + ")"
            )

    def unregister_camera(self, camera_id: int):
        with self._lock:
            state = self._cameras.pop(camera_id, None)
            if state:
                state._stop_event.set()
                state._substream_stop_event.set()
                logger.info(f"Camera unregistered: {state.name} (id={camera_id})")

    def update_shelf_zones(self, camera_id: int, zones: list) -> bool:
        """Hot-swap the shelf zones for a live camera.

        The capture loop reads `state.shelf_zones` on each frame, so the
        new polygons take effect on the next enqueued AI frame with no
        restart.
        """
        with self._lock:
            state = self._cameras.get(camera_id)
            if state is None:
                return False
            state.shelf_zones = list(zones)
            return True

    def _start_capture(self, state: CameraState):
        thread = threading.Thread(
            target=self._capture_loop,
            args=(state,),
            daemon=True,
            name=f"cam-{state.camera_id}-{state.name}",
        )
        state.thread = thread
        thread.start()

    def _start_substream_capture(self, state: CameraState):
        """Start secondary capture thread for AI sub-stream."""
        thread = threading.Thread(
            target=self._substream_capture_loop,
            args=(state,),
            daemon=True,
            name=f"sub-{state.camera_id}-{state.name}",
        )
        state._substream_thread = thread
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
            from app.core.tenancy_context import system_bypass
            from app.db.repository.camera_health import CameraHealthRepository
            from app.db.session import AsyncSessionLocal

            # Background health heartbeat runs with no tenant in
            # context; under TENANCY_RLS_ENFORCED=True it would
            # otherwise fail closed and silently drop the upsert.
            with system_bypass():
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

        self._submit_async(
            _write_health(),
            op="camera_health_heartbeat",
            camera_name=state.name,
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
            from app.core.tenancy_context import system_bypass
            from app.db.repository.camera_health import CameraHealthRepository
            from app.db.session import AsyncSessionLocal

            with system_bypass():
                async with AsyncSessionLocal() as db:
                    await CameraHealthRepository(db).mark_notification_sent(
                        camera_id=state.camera_id,
                        notified_at=datetime.now(UTC),
                    )

        self._submit_async(
            _mark_notification(),
            op="camera_offline_notification",
            camera_name=state.name,
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
                # When a sub-stream is configured the secondary thread handles
                # AI enqueue; skip it here so the same frame isn't processed twice.
                has_substream = bool(state.substream_url)
                if state.is_ai_enabled and not has_substream and ai_counter % skip_n == 0:
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
                        "shelf_zones": state.shelf_zones,
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

    def _substream_capture_loop(self, state: CameraState):
        """Capture loop for the secondary (AI) sub-stream.

        Reads only from `state.substream_url`. Frames are enqueued directly
        to the AI inference queue — no display buffer update (the primary
        stream handles display). Shares the same skip_n / target settings
        as the primary loop so AI cadence stays consistent.
        """
        source = _resolve_source(state.substream_url, state.camera_type)
        if source is None:
            logger.warning(
                "[%s] Sub-stream: no usable video source — staying offline",
                state.name,
            )
            state._substream_connected = False
            return

        logger.info("[%s] Sub-stream: connecting to %s", state.name, source)
        cap = self._open_capture(state, source)
        backoff = self._reconnect_base_backoff()
        max_backoff = self._reconnect_max_backoff()
        skip_n = max(1, settings.AI_FRAME_SKIP)
        target = max(64, settings.AI_INPUT_SIZE)

        ai_counter = 0
        state._substream_connected = cap.isOpened()
        if state._substream_connected:
            logger.info("[%s] Sub-stream: connected", state.name)

        try:
            while not state._substream_stop_event.is_set():
                if not state._substream_connected:
                    if state._substream_stop_event.wait(backoff):
                        break
                    backoff = self._next_reconnect_backoff(backoff, max_backoff)
                    cap.release()
                    cap = self._open_capture(state, source)
                    if cap.isOpened():
                        state._substream_connected = True
                        backoff = self._reconnect_base_backoff()
                        logger.info("[%s] Sub-stream: reconnected", state.name)
                    continue

                success, frame = cap.read()
                if not success:
                    state._substream_connected = False
                    continue

                state._substream_connected = True
                ai_counter += 1
                if state.is_ai_enabled and ai_counter % skip_n == 0:
                    h, w = frame.shape[:2]
                    scale = target / max(h, w)
                    small = (
                        cv2.resize(frame, (int(w * scale), int(h * scale)))
                        if scale < 1.0
                        else frame
                    )
                    # `full_frame` deliberately uses the sub-stream frame so
                    # alert thumbnails are proportional to the AI input even
                    # if the primary stream runs at a different resolution.
                    self._enqueue_ai_frame({
                        "frame": small,
                        "full_frame": frame,
                        "camera_id": state.camera_id,
                        "store_id": state.store_id,
                        "source": state.name,
                        "threshold": state.alert_threshold,
                        "cooldown": state.alert_cooldown,
                        "shelf_zones": state.shelf_zones,
                    })

                time.sleep(0.01)
        except Exception as exc:
            logger.error("[%s] Sub-stream error: %s", state.name, exc)
        finally:
            cap.release()
            state._substream_connected = False
            logger.info("[%s] Sub-stream: capture loop stopped", state.name)

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
            state._substream_stop_event.set()
            with state.frame_condition:
                state.frame_condition.notify_all()

        for state in states:
            if state.thread and state.thread.is_alive():
                state.thread.join(timeout=2.0)
            if state._substream_thread and state._substream_thread.is_alive():
                state._substream_thread.join(timeout=2.0)

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

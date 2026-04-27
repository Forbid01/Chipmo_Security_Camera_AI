"""RTSP capture worker — scaffold for T4-20.

Opens a single RTSP / HTTP camera stream in a background thread,
decodes frames with OpenCV, and forwards each frame to a callback.
Handles reconnect with exponential backoff so a transient camera
outage doesn't take the worker down.

Intentionally narrow:

* One worker = one camera. The supervising loop in `runner.py` spins
  up N workers, one per assigned camera.
* No YOLO inference here — the callback is where the future inference
  queue plugs in. Keeping the boundary crisp means the capture loop
  can be unit-tested without pulling ultralytics into the agent image.
* No per-camera metadata exchange with the server. The worker only
  needs (camera_id, rtsp_url). The server picks which cameras each
  agent runs and ships the list via a future `/agents/{id}/cameras`
  fetch (not wired here).

Shutdown contract: the caller passes the same `threading.Event` that
`runner.run()` sets on SIGTERM. The worker polls the event between
reads so `docker stop` finishes inside the container's grace period.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("sentry_agent.capture")


# Reconnect tuning — kept short enough that a 30-second camera blip
# doesn't cost the operator a visible gap, long enough that a dead
# camera doesn't hammer the network.
RECONNECT_BACKOFF_BASE_S = 1.0
RECONNECT_BACKOFF_CAP_S = 30.0

# Maximum seconds we wait for a single frame before deciding the
# stream is stuck. OpenCV's VideoCapture can wedge silently on some
# RTSP servers; this makes failures visible.
READ_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class FrameEvent:
    """What the callback receives per frame.

    Separate from the raw ndarray so the callback can log / enqueue
    metadata without touching the pixel buffer, and so future fields
    (e.g. decoded timestamp, dropped-frame count) can land without
    churning every callsite.
    """

    camera_id: str
    sequence: int
    frame: Any  # numpy.ndarray — kept generic so this module doesn't import numpy.
    monotonic_ts: float


FrameCallback = Callable[[FrameEvent], None]


class CaptureWorker:
    """Single-camera capture loop that can run in its own thread.

    Typical lifecycle:

        worker = CaptureWorker(camera_id="cam-1", url="rtsp://...", stop=stop_event)
        worker.start(on_frame=queue.put)
        ...
        stop_event.set()
        worker.join()
    """

    def __init__(
        self,
        *,
        camera_id: str,
        url: str,
        stop: threading.Event,
        read_timeout_s: float = READ_TIMEOUT_S,
    ) -> None:
        if not camera_id:
            raise ValueError("camera_id is required")
        if not url:
            raise ValueError("url is required")
        self.camera_id = camera_id
        self.url = url
        self._stop = stop
        self._read_timeout_s = read_timeout_s
        self._thread: threading.Thread | None = None
        self._on_frame: FrameCallback | None = None
        # Keep a small stats surface so the runner can log health
        # without reaching into internals.
        self.frames_read: int = 0
        self.reconnects: int = 0
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, on_frame: FrameCallback) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("worker already started")
        self._on_frame = on_frame
        self._thread = threading.Thread(
            target=self._run,
            name=f"capture-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _open(self) -> Any | None:
        """Open the video capture. Isolated so tests can monkeypatch
        `cv2.VideoCapture` without touching `_run`."""
        # Lazy import — keeps this module importable on dev machines
        # that haven't installed opencv yet (e.g. running unit tests
        # for the pure scheduling logic).
        import cv2  # type: ignore[import-untyped]

        cap = cv2.VideoCapture(self.url)
        if not cap.isOpened():
            return None
        # Bound the internal buffer so a backed-up consumer doesn't
        # cause the decoder to queue stale frames.
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # noqa: BLE001
            # Not all backends honour the hint — safe to ignore.
            pass
        return cap

    def _run(self) -> None:
        assert self._on_frame is not None  # start() guarantees this
        backoff = RECONNECT_BACKOFF_BASE_S
        while not self._stop.is_set():
            cap = self._open()
            if cap is None:
                self.last_error = "open_failed"
                self.reconnects += 1
                logger.warning(
                    "capture_open_failed",
                    extra={"camera_id": self.camera_id, "backoff": backoff},
                )
                self._stop.wait(timeout=backoff)
                backoff = min(backoff * 2, RECONNECT_BACKOFF_CAP_S)
                continue

            # Connected — reset backoff for the next failure window.
            backoff = RECONNECT_BACKOFF_BASE_S
            try:
                self._pump(cap)
            finally:
                try:
                    cap.release()
                except Exception:  # noqa: BLE001
                    pass

        logger.info("capture_stopped", extra={"camera_id": self.camera_id})

    def _pump(self, cap: Any) -> None:
        """Read frames from an open capture until an error or stop."""
        assert self._on_frame is not None
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                self.last_error = "read_failed"
                self.reconnects += 1
                logger.warning(
                    "capture_read_failed",
                    extra={"camera_id": self.camera_id},
                )
                return

            self.frames_read += 1
            event = FrameEvent(
                camera_id=self.camera_id,
                sequence=self.frames_read,
                frame=frame,
                monotonic_ts=time.monotonic(),
            )
            try:
                self._on_frame(event)
            except Exception:  # noqa: BLE001
                # Callback failures must never kill the capture loop —
                # log and keep pumping. A broken consumer is an ops
                # problem to fix, not a reason to drop frames.
                logger.exception(
                    "capture_callback_error",
                    extra={"camera_id": self.camera_id},
                )


__all__ = [
    "CaptureWorker",
    "FrameCallback",
    "FrameEvent",
    "READ_TIMEOUT_S",
    "RECONNECT_BACKOFF_BASE_S",
    "RECONNECT_BACKOFF_CAP_S",
]

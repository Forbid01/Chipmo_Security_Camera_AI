"""Unit tests for `sentry_agent.capture.CaptureWorker` (T4-20 scaffold).

OpenCV's `VideoCapture` can't be driven by a unit test — it opens a
real socket. Tests monkeypatch `_open` with a fake that returns a
scripted frame sequence so we can exercise the loop + reconnect logic
deterministically.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1] / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from sentry_agent.capture import CaptureWorker, FrameEvent  # noqa: E402


class _FakeCapture:
    """A stand-in for `cv2.VideoCapture` that returns N frames and
    then reports EOF. Lets us exercise the worker without OpenCV."""

    def __init__(self, frames: list[object] | None = None):
        self._frames = list(frames or [])
        self._released = False

    def isOpened(self) -> bool:  # noqa: N802 — mirrors OpenCV API
        return True

    def read(self):
        if not self._frames:
            return (False, None)
        return (True, self._frames.pop(0))

    def set(self, _prop: int, _value: int) -> bool:
        return True

    def release(self) -> None:
        self._released = True


# ---------------------------------------------------------------------------
# Construction / input validation
# ---------------------------------------------------------------------------

def test_requires_camera_id():
    stop = threading.Event()
    with pytest.raises(ValueError, match="camera_id"):
        CaptureWorker(camera_id="", url="rtsp://x", stop=stop)


def test_requires_url():
    stop = threading.Event()
    with pytest.raises(ValueError, match="url"):
        CaptureWorker(camera_id="cam-1", url="", stop=stop)


def test_double_start_raises():
    stop = threading.Event()
    w = CaptureWorker(camera_id="cam-1", url="rtsp://x", stop=stop)
    w._open = lambda: _FakeCapture(frames=[])  # type: ignore[method-assign]
    w.start(on_frame=lambda e: None)
    try:
        with pytest.raises(RuntimeError, match="already started"):
            w.start(on_frame=lambda e: None)
    finally:
        stop.set()
        w.join(timeout=2)


# ---------------------------------------------------------------------------
# Frame pump — callback receives FrameEvent with increasing sequence
# ---------------------------------------------------------------------------

def test_forwards_each_frame_to_callback():
    stop = threading.Event()
    frames = ["frame-a", "frame-b", "frame-c"]
    w = CaptureWorker(camera_id="cam-1", url="rtsp://x", stop=stop)
    # _open returns ONE capture, after which _pump falls through
    # (because read_failed) and _run tries to reopen. Stop the event
    # once we've seen all three frames.
    w._open = lambda: _FakeCapture(frames=list(frames))  # type: ignore[method-assign]

    received: list[FrameEvent] = []

    def on_frame(evt: FrameEvent) -> None:
        received.append(evt)
        if len(received) >= 3:
            stop.set()

    w.start(on_frame=on_frame)
    w.join(timeout=2)

    assert [e.frame for e in received] == frames
    assert [e.sequence for e in received] == [1, 2, 3]
    assert all(e.camera_id == "cam-1" for e in received)
    assert w.frames_read == 3


def test_callback_exception_does_not_kill_worker():
    """A broken consumer must not take the capture loop down."""
    stop = threading.Event()
    frames = ["a", "b", "c"]
    w = CaptureWorker(camera_id="cam-1", url="rtsp://x", stop=stop)
    w._open = lambda: _FakeCapture(frames=list(frames))  # type: ignore[method-assign]

    calls = {"n": 0}

    def on_frame(_evt: FrameEvent) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("consumer is grumpy")
        if calls["n"] >= 3:
            stop.set()

    w.start(on_frame=on_frame)
    w.join(timeout=2)
    # The worker kept going past the exception and read all 3 frames.
    assert calls["n"] == 3


# ---------------------------------------------------------------------------
# Reconnect — open failure triggers backoff + retry, then success.
# ---------------------------------------------------------------------------

def test_reconnects_when_open_fails_initially():
    stop = threading.Event()
    w = CaptureWorker(
        camera_id="cam-1",
        url="rtsp://x",
        stop=stop,
        read_timeout_s=1.0,
    )

    attempts = {"n": 0}

    def fake_open():
        attempts["n"] += 1
        if attempts["n"] < 2:
            return None  # open_failed → backoff → retry
        return _FakeCapture(frames=["only-frame"])

    w._open = fake_open  # type: ignore[method-assign]

    received: list[FrameEvent] = []

    def on_frame(evt: FrameEvent) -> None:
        received.append(evt)
        stop.set()

    # Monkey-patch the backoff base via the module constant so the test
    # doesn't actually wait seconds. The worker reads the constant at
    # call time, not import time.
    from sentry_agent import capture

    original = capture.RECONNECT_BACKOFF_BASE_S
    capture.RECONNECT_BACKOFF_BASE_S = 0.05
    try:
        w.start(on_frame=on_frame)
        w.join(timeout=3)
    finally:
        capture.RECONNECT_BACKOFF_BASE_S = original

    assert len(received) == 1
    assert received[0].frame == "only-frame"
    assert w.reconnects >= 1
    assert w.last_error is not None


# ---------------------------------------------------------------------------
# Shutdown — setting stop causes the worker to exit promptly.
# ---------------------------------------------------------------------------

def test_stop_event_exits_worker_promptly():
    stop = threading.Event()
    w = CaptureWorker(camera_id="cam-1", url="rtsp://x", stop=stop)
    # Infinite frame stream — only the stop event can break the loop.

    class _Infinite:
        def isOpened(self): return True  # noqa: N802
        def read(self): return (True, "x")
        def set(self, *a): return True
        def release(self): pass

    w._open = lambda: _Infinite()  # type: ignore[method-assign]
    w.start(on_frame=lambda e: None)
    # Let it get a few frames in flight.
    time.sleep(0.05)
    stop.set()
    w.join(timeout=2)
    assert not w.is_alive(), "worker must exit within 2s of stop.set()"

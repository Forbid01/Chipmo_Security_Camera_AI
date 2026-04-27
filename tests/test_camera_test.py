"""T4-11 — camera_test service + POST /cameras/test endpoint.

Fake-capture harness lets us assert the full decode + thumbnail +
FPS pipeline without a live RTSP stream. The endpoint test mirrors
the same setup through FastAPI's TestClient with tenant override.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-camera-test")

from app.services import camera_test  # noqa: E402


# ---------------------------------------------------------------------------
# Fake cv2.VideoCapture — scripted frame sequence
# ---------------------------------------------------------------------------

class _FakeFrame:
    """Tiny stand-in for a numpy ndarray; provides `.shape` so the
    service's `_shape2` helper works without importing numpy."""

    def __init__(self, height: int, width: int, channels: int = 3):
        self.shape = (height, width, channels)


class _FakeCapture:
    def __init__(
        self,
        *,
        frames: list[_FakeFrame | None],
        opened: bool = True,
    ):
        self._frames = list(frames)
        self._opened = opened
        self.released = False
        self.reads = 0

    def isOpened(self) -> bool:
        return self._opened

    def read(self):
        self.reads += 1
        if not self._frames:
            return False, None
        frame = self._frames.pop(0)
        if frame is None:
            return False, None
        return True, frame

    def release(self):
        self.released = True


def _noop_encoder(_frame) -> bytes:
    return b"\xff\xd8\xffJPEGFAKE"


# Inject a monotonic clock that returns a fixed sequence so FPS
# estimation is deterministic in tests.
class _Ticker:
    def __init__(self, values):
        self._values = list(values)

    def __call__(self):
        return self._values.pop(0) if self._values else 1e9


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

class TestTestCamera:
    def test_happy_path_returns_thumbnail_b64_and_fps(self):
        # Use a 320x240 frame so the `_maybe_shrink` path is a no-op
        # (our FakeFrame isn't a numpy ndarray so actual cv2.resize
        # would return the original anyway — covered by
        # test_small_frame_not_shrunk).
        cap = _FakeCapture(frames=[
            _FakeFrame(240, 320),
            _FakeFrame(240, 320),
            _FakeFrame(240, 320),
            _FakeFrame(240, 320),
        ])
        ticker = _Ticker([
            0.0,    # start of test_camera
            0.0,    # start of _estimate_fps
            0.5,    # still before deadline
            1.0,    # still before deadline
            1.6,    # past deadline
            1.6,    # elapsed
            1.6,    # latency_ms
        ])

        result = camera_test.test_camera(
            "rtsp://user:pw@10.0.0.5:554/stream",
            capture_factory=lambda _url: cap,
            jpeg_encoder=_noop_encoder,
            clock=ticker,
            fps_window_s=1.5,
        )

        assert result.ok is True, result.message
        assert result.thumbnail_b64 == base64.b64encode(b"\xff\xd8\xffJPEGFAKE").decode()
        assert result.thumbnail_width == 320
        assert result.thumbnail_height == 240
        assert result.fps is not None and result.fps > 0
        assert result.latency_ms is not None
        assert cap.released, "capture must be released on success"

    def test_closed_stream_reports_failure_with_hints(self):
        cap = _FakeCapture(frames=[], opened=False)
        result = camera_test.test_camera(
            "rtsp://user:pw@x/stream",
            manufacturer_id="hikvision",
            capture_factory=lambda _url: cap,
            jpeg_encoder=_noop_encoder,
        )
        assert result.ok is False
        assert "stream" in result.message.lower()
        # Hikvision factory default hints surfaced on failure.
        assert result.credential_hints is not None
        assert any(h["username"] == "admin" for h in result.credential_hints)

    def test_no_frame_read_returns_failure_without_crash(self):
        cap = _FakeCapture(frames=[None])   # first read returns (False, None)
        result = camera_test.test_camera(
            "rtsp://x/y",
            capture_factory=lambda _url: cap,
            jpeg_encoder=_noop_encoder,
        )
        assert result.ok is False
        assert "frame" in result.message.lower()
        assert cap.released

    def test_unknown_manufacturer_no_hints(self):
        cap = _FakeCapture(frames=[], opened=False)
        result = camera_test.test_camera(
            "rtsp://x",
            manufacturer_id=None,
            capture_factory=lambda _url: cap,
            jpeg_encoder=_noop_encoder,
        )
        assert result.ok is False
        assert result.credential_hints is None

    def test_capture_factory_exception_does_not_propagate(self):
        def _explode(_url):
            raise RuntimeError("cv2 not installed")

        result = camera_test.test_camera(
            "rtsp://x",
            capture_factory=_explode,
            jpeg_encoder=_noop_encoder,
        )
        # Must return a structured failure, never raise.
        assert result.ok is False
        assert "Камер" in result.message or "шалгана" in result.message

    def test_small_frame_not_shrunk(self):
        """A 320x240 frame should stay at 320x240 — we only resize
        when width > max_thumbnail_width."""
        cap = _FakeCapture(frames=[_FakeFrame(240, 320)] * 10)
        result = camera_test.test_camera(
            "rtsp://x",
            capture_factory=lambda _url: cap,
            jpeg_encoder=_noop_encoder,
            fps_window_s=0.01,
        )
        assert result.ok is True
        assert result.thumbnail_width == 320
        assert result.thumbnail_height == 240


class TestRedactLogging:
    def test_user_password_stripped_from_logged_url(self):
        from app.services.camera_test import _redact
        redacted = _redact("rtsp://admin:hunter2@192.168.1.5:554/stream")
        assert "hunter2" not in redacted
        assert "<redacted>" in redacted
        assert "192.168.1.5" in redacted


# ---------------------------------------------------------------------------
# Endpoint — POST /api/v1/cameras/test
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def scalar_one_or_none(self):
        return None


class _FakeDB:
    async def execute(self, _query, _params=None):
        return _FakeResult()

    async def commit(self):
        pass


@pytest.fixture
def fake_app(monkeypatch):
    from app.api.v1 import cameras  # noqa: PLC0415
    from app.core.tenant_auth import get_current_tenant  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()
    app.include_router(cameras.router, prefix="/api/v1/cameras")

    async def _db_override():
        yield _FakeDB()

    async def _tenant_override():
        return {"tenant_id": "11111111-2222-3333-4444-555555555555", "status": "active"}

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_tenant] = _tenant_override

    # Replace the real OpenCV-backed test with a deterministic stub.
    def _stub(url, *, manufacturer_id=None, **_kw):
        from app.services.camera_test import CameraTestResult

        if "unreachable" in url:
            return CameraTestResult(
                ok=False,
                message="timeout",
                credential_hints=[{"username": "admin", "password": "12345", "note": "hint"}]
                if manufacturer_id == "hikvision" else None,
            )
        return CameraTestResult(
            ok=True, message="ok",
            thumbnail_b64="ZmFrZQ==",
            thumbnail_width=640, thumbnail_height=360,
            fps=15.0, latency_ms=120.0,
        )

    monkeypatch.setattr(cameras, "run_camera_test", _stub)
    return app


def test_endpoint_happy_path(fake_app):
    from fastapi.testclient import TestClient

    client = TestClient(fake_app)
    resp = client.post(
        "/api/v1/cameras/test",
        json={"url": "rtsp://admin:pw@10.0.0.5/main"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["fps"] == 15.0
    assert body["thumbnail_b64"] == "ZmFrZQ=="


def test_endpoint_failure_returns_hints(fake_app):
    from fastapi.testclient import TestClient

    client = TestClient(fake_app)
    resp = client.post(
        "/api/v1/cameras/test",
        json={
            "url": "rtsp://admin:pw@unreachable.example/main",
            "manufacturer_id": "hikvision",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["credential_hints"], "hikvision hints expected on failure"


def test_endpoint_rejects_bad_request(fake_app):
    from fastapi.testclient import TestClient

    client = TestClient(fake_app)
    resp = client.post("/api/v1/cameras/test", json={})
    assert resp.status_code == 422

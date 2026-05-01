"""RTSP test-connection helper (T4-11).

Backend-side frame grab used by the customer-portal "Test camera"
button. Opens the stream with OpenCV, reads one frame, JPEG-encodes
it as a thumbnail, measures an FPS estimate from a short sample
window, then closes — never keeps an open pull on the camera.

Separated from the FastAPI handler so unit tests can inject a fake
`cv2.VideoCapture` factory without spinning up a live stream.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structural typing so tests don't pull in cv2.
# ---------------------------------------------------------------------------

class VideoCaptureLike(Protocol):
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...


class FrameEncoderLike(Protocol):
    def __call__(self, frame: Any) -> bytes: ...


CaptureFactory = Callable[[str], VideoCaptureLike]


@dataclass(frozen=True)
class CameraTestResult:
    ok: bool
    message: str
    thumbnail_b64: str | None = None
    thumbnail_width: int | None = None
    thumbnail_height: int | None = None
    fps: float | None = None
    latency_ms: float | None = None
    credential_hints: list[dict[str, Any]] | None = None
    # Machine-readable failure reason so the UI can show specific guidance.
    # "network"  — camera not reachable at all (wrong IP/port/URL path).
    # "auth"     — connection opened but no frames (bad credentials or codec).
    # "encode"   — frame grabbed but JPEG encoding failed.
    error_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "thumbnail_b64": self.thumbnail_b64,
            "thumbnail_width": self.thumbnail_width,
            "thumbnail_height": self.thumbnail_height,
            "fps": self.fps,
            "latency_ms": self.latency_ms,
            "credential_hints": self.credential_hints,
            "error_category": self.error_category,
        }


# ---------------------------------------------------------------------------
# Default implementations — lazy cv2 import so the module loads on
# systems without OpenCV (CI, type-check).
# ---------------------------------------------------------------------------

def _default_capture_factory(url: str) -> VideoCaptureLike:
    import cv2  # type: ignore[import-not-found]

    # CAP_FFMPEG forces the FFmpeg backend, which is the only one that
    # handles RTSP reliably across Linux/Windows/macOS.
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG)


def _default_jpeg_encoder(frame: Any) -> bytes:
    import cv2  # type: ignore[import-not-found]

    # 60 is a sweet spot for a UI thumbnail — file fits comfortably in
    # a JSON response (<50KB for typical 1080p frames).
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


# ---------------------------------------------------------------------------
# Test flow
# ---------------------------------------------------------------------------

def test_camera(
    url: str,
    *,
    manufacturer_id: str | None = None,
    fps_window_s: float = 1.5,
    max_thumbnail_width: int = 640,
    capture_factory: CaptureFactory | None = None,
    jpeg_encoder: FrameEncoderLike | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> CameraTestResult:
    """Probe a single RTSP URL. Never raises — always returns a
    structured `CameraTestResult` so the HTTP handler can wrap it
    without try/except noise."""

    capture_factory = capture_factory or _default_capture_factory
    jpeg_encoder = jpeg_encoder or _default_jpeg_encoder

    start = clock()
    try:
        cap = capture_factory(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("camera_test_open_failed", extra={"url": _redact(url), "err": str(exc)})
        return _fail(
            "Холбогдож чадсангүй — IP хаяг, порт эсвэл URL зам буруу байж болно.",
            manufacturer_id,
            error_category="network",
        )

    try:
        if not cap.isOpened():
            return _fail(
                "Холбогдож чадсангүй — IP хаяг, порт эсвэл URL зам буруу байж болно.",
                manufacturer_id,
                error_category="network",
            )

        ok, frame = cap.read()
        if not ok or frame is None:
            return _fail(
                "Холболт нээгдсэн боловч stream ирсэнгүй — "
                "нэвтрэх нэр/нууц үг буруу эсвэл codec тохирохгүй байна.",
                manufacturer_id,
                error_category="auth",
            )

        # Thumbnail shrink — big frames bloat JSON and slow the UI.
        try:
            height, width = frame.shape[:2]
        except Exception:
            height, width = (None, None)

        try:
            thumb_frame = _maybe_shrink(frame, max_thumbnail_width)
            jpeg_bytes = jpeg_encoder(thumb_frame)
            thumb_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
            t_h, t_w = _shape2(thumb_frame, fallback=(height, width))
        except Exception as exc:  # noqa: BLE001
            logger.warning("camera_test_encode_failed", extra={"err": str(exc)})
            return _fail(
                "Frame уншигдсан боловч JPEG кодлоход алдаа гарлаа.",
                manufacturer_id,
                error_category="encode",
            )

        fps = _estimate_fps(cap, window_s=fps_window_s, clock=clock)

        latency_ms = (clock() - start) * 1000.0
        return CameraTestResult(
            ok=True,
            message="Камер амжилттай холбогдлоо.",
            thumbnail_b64=thumb_b64,
            thumbnail_width=t_w,
            thumbnail_height=t_h,
            fps=fps,
            latency_ms=latency_ms,
        )
    finally:
        try:
            cap.release()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fail(
    message: str,
    manufacturer_id: str | None,
    *,
    error_category: str | None = None,
) -> CameraTestResult:
    return CameraTestResult(
        ok=False,
        message=message,
        credential_hints=_hints_for(manufacturer_id),
        error_category=error_category,
    )


def _hints_for(manufacturer_id: str | None) -> list[dict[str, Any]] | None:
    """T4-14 integration — on failure, surface the factory-default
    credentials for the detected manufacturer so the customer can try
    them in the UI form. `None` when we have no hints (unknown vendor)."""
    if not manufacturer_id:
        return None
    try:
        from app.services import rtsp_patterns
    except ImportError:
        return None
    hints = rtsp_patterns.credential_hints(manufacturer_id)
    return hints or None


def _maybe_shrink(frame: Any, max_w: int) -> Any:
    """Resize a frame to max_w px wide, preserving aspect ratio.

    Returns the original frame when cv2 isn't importable OR the
    resize call raises (e.g. non-ndarray duck-typed test fixtures).
    """
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return frame
    try:
        h, w = frame.shape[:2]
    except Exception:
        return frame
    if w <= max_w:
        return frame
    scale = max_w / float(w)
    new_size = (max_w, int(h * scale))
    try:
        return cv2.resize(frame, new_size)
    except Exception:
        return frame


def _shape2(frame: Any, *, fallback) -> tuple[int | None, int | None]:
    try:
        h, w = frame.shape[:2]
        return int(h), int(w)
    except Exception:
        return fallback


def _estimate_fps(
    cap: VideoCaptureLike,
    *,
    window_s: float,
    clock: Callable[[], float],
) -> float:
    """Count how many frames we can read in `window_s` wall seconds.

    This is deliberately a wall-clock estimate (not cap.get(CAP_PROP_FPS))
    — many RTSP cameras advertise 30 FPS in their profile but deliver
    significantly fewer in practice due to bandwidth caps.
    """
    frames = 0
    start = clock()
    deadline = start + max(window_s, 0.1)
    while clock() < deadline:
        ok, _ = cap.read()
        if not ok:
            break
        frames += 1
    elapsed = max(clock() - start, 1e-6)
    return round(frames / elapsed, 1)


def _redact(url: str) -> str:
    """Strip user:password from rtsp URLs before logging."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        _, host = rest.split("@", 1)
        return f"{scheme}://<redacted>@{host}"
    return url


__all__ = [
    "CameraTestResult",
    "test_camera",
]

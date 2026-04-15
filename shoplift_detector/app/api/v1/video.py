import asyncio
import time

import cv2
import numpy as np
from app.core.security import CurrentUser
from app.services.camera_manager import camera_manager
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

# Target ~15 FPS to the browser. AI-annotated dashboards don't benefit from
# 30 FPS — the bottleneck is JPEG encode + network + <img> decode. Sending
# half the frames cuts CPU and bandwidth roughly in half with no visible loss.
STREAM_FPS = 15
STREAM_FRAME_INTERVAL = 1.0 / STREAM_FPS
JPEG_QUALITY = 75


async def generate_camera_frames(camera_id: int):
    last_sent = 0.0
    last_frame_id = None
    while True:
        now = time.monotonic()
        wait = STREAM_FRAME_INTERVAL - (now - last_sent)
        if wait > 0:
            await asyncio.sleep(wait)

        frame = camera_manager.get_frame(camera_id)
        if frame is None:
            await asyncio.sleep(0.1)
            continue

        # Skip re-encoding when the AI thread hasn't produced a new frame yet.
        # id() is stable within the deque slot lifetime and cheap to compare.
        frame_id = id(frame)
        if frame_id == last_frame_id:
            await asyncio.sleep(STREAM_FRAME_INTERVAL / 2)
            continue
        last_frame_id = frame_id

        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ret:
            continue

        last_sent = time.monotonic()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )


async def generate_store_frames(store_id: int):
    """Дэлгүүрийн бүх камерыг нэг grid-д нэгтгэж stream хийх."""
    last_sent = 0.0
    while True:
        now = time.monotonic()
        wait = STREAM_FRAME_INTERVAL - (now - last_sent)
        if wait > 0:
            await asyncio.sleep(wait)

        frames = camera_manager.get_store_frames(store_id)
        if not frames:
            await asyncio.sleep(0.1)
            continue

        if len(frames) == 1:
            combined = frames[0]
        else:
            target_h = 480
            resized = []
            for f in frames[:4]:
                h, w = f.shape[:2]
                scale = target_h / h
                resized.append(cv2.resize(f, (int(w * scale), target_h)))

            if len(resized) <= 2:
                max_w = max(r.shape[1] for r in resized)
                padded = []
                for r in resized:
                    if r.shape[1] < max_w:
                        pad = np.zeros((target_h, max_w - r.shape[1], 3), dtype=np.uint8)
                        r = np.hstack([r, pad])
                    padded.append(r)
                combined = np.hstack(padded)
            else:
                row1 = np.hstack(resized[:2])
                row2_frames = resized[2:4]
                while len(row2_frames) < 2:
                    row2_frames.append(np.zeros_like(resized[0]))
                row2 = np.hstack(row2_frames)
                min_w = min(row1.shape[1], row2.shape[1])
                row1 = row1[:, :min_w]
                row2 = row2[:, :min_w]
                combined = np.vstack([row1, row2])

        ret, buffer = cv2.imencode(".jpg", combined, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ret:
            last_sent = time.monotonic()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )


@router.get("/feed/{camera_id}")
async def video_feed(camera_id: int, user: CurrentUser):
    """Нэг камерын live stream (authenticated)."""
    return StreamingResponse(
        generate_camera_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/store/{store_id}")
async def store_video_feed(store_id: int, user: CurrentUser):
    """Дэлгүүрийн бүх камерыг grid-д нэгтгэсэн stream."""
    return StreamingResponse(
        generate_store_frames(store_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

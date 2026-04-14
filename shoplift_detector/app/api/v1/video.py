import asyncio
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.services.camera_manager import camera_manager

router = APIRouter()


async def generate_camera_frames(camera_id: int):
    while True:
        frame = camera_manager.get_frame(camera_id)
        if frame is None:
            await asyncio.sleep(0.1)
            continue

        ret, buffer = cv2.imencode(".jpg", frame.copy(), [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            await asyncio.sleep(0.03)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )
        await asyncio.sleep(0.033)


async def generate_store_frames(store_id: int):
    """Дэлгүүрийн бүх камерыг нэг grid-д нэгтгэж stream хийх."""
    while True:
        frames = camera_manager.get_store_frames(store_id)
        if not frames:
            await asyncio.sleep(0.1)
            continue

        if len(frames) == 1:
            combined = frames[0]
        else:
            # Grid layout
            target_h = 480
            resized = []
            for f in frames[:4]:  # Max 4 cameras in grid
                h, w = f.shape[:2]
                scale = target_h / h
                resized.append(cv2.resize(f, (int(w * scale), target_h)))

            if len(resized) <= 2:
                # Fill with black if widths differ
                max_w = max(r.shape[1] for r in resized)
                padded = []
                for r in resized:
                    if r.shape[1] < max_w:
                        pad = np.zeros((target_h, max_w - r.shape[1], 3), dtype=np.uint8)
                        r = np.hstack([r, pad])
                    padded.append(r)
                combined = np.hstack(padded)
            else:
                # 2x2 grid
                row1 = np.hstack(resized[:2])
                row2_frames = resized[2:4]
                while len(row2_frames) < 2:
                    row2_frames.append(np.zeros_like(resized[0]))
                row2 = np.hstack(row2_frames)
                # Match widths
                min_w = min(row1.shape[1], row2.shape[1])
                row1 = row1[:, :min_w]
                row2 = row2[:, :min_w]
                combined = np.vstack([row1, row2])

        ret, buffer = cv2.imencode(".jpg", combined, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
        await asyncio.sleep(0.033)


@router.get("/feed/{camera_id}")
async def video_feed(
    camera_id: int,
    user: dict = Depends(get_current_user),
):
    """Нэг камерын live stream (authenticated)."""
    return StreamingResponse(
        generate_camera_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/store/{store_id}")
async def store_video_feed(
    store_id: int,
    user: dict = Depends(get_current_user),
):
    """Дэлгүүрийн бүх камерыг grid-д нэгтгэсэн stream."""
    return StreamingResponse(
        generate_store_frames(store_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

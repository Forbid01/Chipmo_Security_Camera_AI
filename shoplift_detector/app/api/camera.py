from __future__ import annotations

import asyncio

import app.core.state as state
import cv2
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter()

async def gen_frames(camera_id: str):
    while True:
        # Lock байхгүй — шууд уншина (GIL хамгаална)
        if camera_id == "mac":
            frame = state.latest_mac_frame
        elif camera_id == "phone":
            frame = state.latest_phone_frame
        elif camera_id == "axis":
            frame = state.latest_axis_frame
        else:
            frame = None

        if frame is None:
            await asyncio.sleep(0.1)
            continue

        # Уншсаны дараа copy — AI дарж бичсэн ч асуудалгүй
        frame = frame.copy()

        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        await asyncio.sleep(0.033)

@router.get("/video_feed/{camera_id}")
async def video_feed(camera_id: str):
    if camera_id not in ["mac", "phone", "axis"]:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй")

    return StreamingResponse(
        gen_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

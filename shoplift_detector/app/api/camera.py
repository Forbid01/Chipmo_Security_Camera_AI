# app/api/camera.py

import asyncio
import cv2
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import app.core.state as state

router = APIRouter()

async def gen_frames(camera_id: str):
    while True:
        frame = None
        if camera_id == "mac":
            frame = state.latest_mac_frame
        elif camera_id == "phone":
            frame = state.latest_phone_frame
        elif camera_id == "drone":
            frame = state.latest_drone_frame
        
        if frame is None:
            await asyncio.sleep(0.1)
            continue

        # Зургийг JPEG рүү хөрвүүлэх
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            continue
            
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        # 30 FPS хурдыг барих
        await asyncio.sleep(0.033)

@router.get("/video_feed/{camera_id}")
async def video_feed(camera_id: str):
    if camera_id not in ["mac", "phone", "drone"]:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй")
        
    return StreamingResponse(
        gen_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
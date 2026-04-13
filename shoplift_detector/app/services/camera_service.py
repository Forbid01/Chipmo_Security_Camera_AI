import cv2
import time
import queue
import logging
import threading
import asyncio
import app.core.state as state
from app.core.config import DEFAULT_CAMERA_SOURCES
from app.db.repository.users import UserRepository

logger = logging.getLogger(__name__)
user_repo = UserRepository()

CAMERA_NAME_MAP = {
    "mac": "Mac-Camera",
    "phone": "Phone-Camera",
    "axis": "Axis-Camera",
}

def capture_stream(source, camera_name):
    if not source and source != 0:
        logger.warning(f"{camera_name}: URL тохируулаагүй байна. Алгасаж байна.")
        return

    logger.info(f"{camera_name} холбогдож байна: {source}")
    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        logger.error(f"{camera_name}: Холболт амжилтгүй.")
        return

    logger.info(f"{camera_name} амжилттай холбогдлоо.")

    try:
        while True:
            success, frame = cap.read()
            if not success:
                logger.warning(f"{camera_name} тасарлаа. Дахин холбогдож байна...")
                time.sleep(2)
                cap.open(source)
                continue

            if camera_name == "Mac-Camera":
                state.latest_mac_frame = frame.copy()
            elif camera_name == "Phone-Camera":
                state.latest_phone_frame = frame.copy()
            elif camera_name == "Axis-Camera":
                state.latest_axis_frame = frame.copy()

            if camera_name in ["Mac-Camera", "Axis-Camera"]:
                if not state.ai_input_queue.full():
                    try:
                        state.ai_input_queue.put({
                            "frame": frame.copy(),
                            "source": camera_name
                        }, block=False)
                    except queue.Full:
                        pass

            if camera_name in ["Mac-Camera", "Axis-Camera"]:
                with state.buffer_lock:
                    state.video_buffer.append(frame.copy())

            time.sleep(0.02)
    except Exception as e:
        logger.error(f"{camera_name} Exception: {e}")
    finally:
        cap.release()

async def load_camera_sources():
    camera_sources = []

    # 1. Default эх сурвалжууд
    for camera_type, source in DEFAULT_CAMERA_SOURCES.items():
        if source or source == 0:
            camera_sources.append((source, CAMERA_NAME_MAP.get(camera_type, "Unknown")))

    try:
        cameras = await user_repo.get_all_cameras()
        logger.info(f"DB-ээс {len(cameras)} камерын мэдээлэл авлаа.")
    except Exception as exc:
        logger.error(f"DB-с камерын тохиргоо уншихад алдаа: {exc}")
        cameras = []

    for camera in cameras:
        camera_type = (camera.get("type") or "").strip().lower()
        source = camera.get("url")
        name = camera.get("name") or CAMERA_NAME_MAP.get(camera_type, "External-Camera")

        if not source:
            continue

        existing_index = next(
            (idx for idx, (_, existing_name) in enumerate(camera_sources) if existing_name == name),
            None,
        )

        resolved = (source, name)
        if existing_index is None:
            camera_sources.append(resolved)
        else:
            camera_sources[existing_index] = resolved

    return camera_sources


def video_capture():
    """Sync thread дотор ажиллах үндсэн функц"""
    # 1. Async логикийг ажиллуулах шинэ loop үүсгэх
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 2. load_camera_sources-ыг дуустал нь хүлээж үр дүнг авах
        sources = loop.run_until_complete(load_camera_sources())
        
        threads = []
        for source, camera_name in sources:
            thread = threading.Thread(
                target=capture_stream,
                args=(source, camera_name),
                daemon=True,
                name=f"Thread-{camera_name}"
            )
            thread.start()
            threads.append(thread)

        logger.info(f"{len(threads)} камерын дамжуулалт амжилттай эхэллээ.")
        
        for thread in threads:
            thread.join()
            
    except Exception as e:
        logger.error(f"video_capture алдаа: {e}")
    finally:
        loop.close()
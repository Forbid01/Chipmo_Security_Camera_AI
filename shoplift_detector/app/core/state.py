"""Global state - backward compatibility layer.
New code should use camera_manager instead."""

import queue
import threading
from collections import deque

VIDEO_BUFFER_MAXLEN = 150

video_buffer = deque(maxlen=VIDEO_BUFFER_MAXLEN)
ai_input_queue = queue.Queue(maxsize=4)
web_display_queue = queue.Queue(maxsize=1)
alert_queue = queue.Queue(maxsize=100)

latest_mac_frame = None
latest_phone_frame = None
latest_axis_frame = None

buffer_lock = threading.Lock()


def add_to_video_buffer(frame):
    if frame is not None:
        with buffer_lock:
            video_buffer.append(frame.copy())


def get_video_buffer_snapshot():
    with buffer_lock:
        return list(video_buffer)


def clear_all_queues():
    for q in [ai_input_queue, web_display_queue]:
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break


def safe_update_display_queue(frame, source: str = "Mac-Camera"):
    global latest_mac_frame, latest_phone_frame, latest_axis_frame

    if frame is None:
        return

    if source == "Mac-Camera":
        latest_mac_frame = frame
    elif source == "Phone-Camera":
        latest_phone_frame = frame
    elif source == "Axis-Camera":
        latest_axis_frame = frame


def get_latest_frame(camera_id: str):
    if camera_id == "mac":
        return latest_mac_frame
    if camera_id == "phone":
        return latest_phone_frame
    if camera_id == "axis":
        return latest_axis_frame
    return None

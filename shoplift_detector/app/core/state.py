import queue
import threading
from collections import deque

VIDEO_BUFFER_MAXLEN = 150

video_buffer = deque(maxlen=VIDEO_BUFFER_MAXLEN)
ai_input_queue = queue.Queue(maxsize=1)
web_display_queue = queue.Queue(maxsize=1)
alert_queue = queue.Queue()

latest_mac_frame = None
latest_phone_frame = None

buffer_lock = threading.Lock()
# display_lock-г УСТГАВ — asyncio-той зөрчилддөг байсан


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


def safe_update_display_queue(frame):
    """
    AI-ийн border зурсан frame-ийг latest_mac_frame-д шууд хадгална.
    CPython-д numpy array assignment нь GIL-ээр хамгаалагддаг тул
    тусдаа lock шаардлагагүй.
    """
    global latest_mac_frame

    if frame is None:
        return

    # GIL-ийн ачаар энэ assignment атомик — lock шаардлагагүй
    latest_mac_frame = frame
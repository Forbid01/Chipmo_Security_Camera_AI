import queue
import threading
from collections import deque

# 150 фрейм нь 25-30 FPS-тэй камерын хувьд ойролцоогоор 5-6 секунд болно.
VIDEO_BUFFER_MAXLEN = 150

# 1. Бичлэг тасдаж авахад зориулсан видео буфер
video_buffer = deque(maxlen=VIDEO_BUFFER_MAXLEN)

# 2. AI процесс руу фрейм дамжуулах дараалал
# maxsize=1 байгаа нь AI өмнөх фреймээ бодож дуусаагүй байхад шинэ фреймүүд овоорохоос сэргийлнэ.
ai_input_queue = queue.Queue(maxsize=1)

# 3. Вэб фронтенд рүү боловсруулсан (Box-той) дүрс дамжуулах
web_display_queue = queue.Queue(maxsize=1)

# 4. Илэрсэн Alert-уудыг WebSocket эсвэл Dashboard руу шидэх
alert_queue = queue.Queue()

# --- СҮҮЛИЙН ҮЕИЙН ФРЕЙМҮҮД (Global State) ---
latest_mac_frame = None
latest_phone_frame = None

# --- LOCKS ---
buffer_lock = threading.Lock()


# --- ТУСЛАХ ФУНКЦҮҮД ---

def add_to_video_buffer(frame):
    """
    Камераас авсан дүрсийг буферт нэмэх функц.
    AI-ийн зураас, Box зурагдахаас өмнөх "ЦЭВЭР" дүрсийг хадгалах ёстой.
    """
    if frame is not None:
        with buffer_lock:
            video_buffer.append(frame.copy())


def get_video_buffer_snapshot():
    """
    Сэжигтэй үйлдэл илрэх үед одоо байгаа буферийг бүхэлд нь хуулж авах.
    """
    with buffer_lock:
        return list(video_buffer)


def clear_all_queues():
    """Бүх дарааллуудыг цэвэрлэх."""
    for q in [ai_input_queue, web_display_queue]:
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break

    # ЗАСВАР ④: web_display_queue-д атомик солилт
    # get + put хоёрын хооронд өөр thread орохоос сэргийлэхийн тулд
    # энэ функцийг ашиглана.


def safe_update_display_queue(frame):
    """
    ЗАСВАР ④: web_display_queue-г аюулгүйгээр шинэчлэх.
    get_nowait() болон put() хоёрын хооронд race condition үүсэхээс сэргийлнэ.
    """
    try:
        # Хуучин фреймийг гаргах (байгаа бол)
        try:
            web_display_queue.get_nowait()
        except queue.Empty:
            pass
        # Шинэ фреймийг оруулах
        web_display_queue.put_nowait(frame)
    except queue.Full:
        pass  # Дүүрсэн бол алгасна — дараагийн фрейм ирнэ
import cv2
import time
import queue
import threading
import app.core.state as state

WIFI_CAMERA_URL  = "http://192.168.0.207:4747/video"
AXIS_CAMERA_URL  = "http://185.194.123.84:8001/axis-cgi/mjpg/video.cgi"
MAC_CAMERA_INDEX = 0


def capture_stream(source, camera_name):
    print(f" {camera_name} холбогдож байна: {source}")
    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f" {camera_name} Error: Холболт амжилтгүй.")
        return

    print(f" {camera_name} амжилттай холбогдлоо.")

    try:
        while True:
            success, frame = cap.read()

            if not success:
                print(f" {camera_name} тасарлаа. Дахин холбогдож байна...")
                time.sleep(2)
                cap.open(source)
                continue

            # 1. Стриминг frame шинэчлэх
            if camera_name == "Mac-Camera":
                if state.latest_mac_frame is None:
                    state.latest_mac_frame = frame.copy()
            elif camera_name == "Phone-Camera":
                state.latest_phone_frame = frame.copy()
            elif camera_name == "Axis-Camera":
                if state.latest_axis_frame is None:
                    state.latest_axis_frame = frame.copy()

            # 2. AI руу илгээх (Mac болон Axis)
            if camera_name in ["Mac-Camera", "Axis-Camera"]:
                if not state.ai_input_queue.full():
                    try:
                        state.ai_input_queue.put({
                            "frame": frame.copy(),
                            "source": camera_name
                        }, block=False)
                    except queue.Full:
                        pass

            # 3. Бичлэгийн буфер
            if camera_name in ["Mac-Camera", "Axis-Camera"]:
                with state.buffer_lock:
                    state.video_buffer.append(frame.copy())

            time.sleep(0.02)

    except Exception as e:
        print(f" {camera_name} Exception: {e}")
    finally:
        cap.release()
        print(f" {camera_name} холболт хаагдлаа.")


def video_capture():
    mac_thread = threading.Thread(
        target=capture_stream,
        args=(MAC_CAMERA_INDEX, "Mac-Camera"),
        daemon=True
    )
    phone_thread = threading.Thread(
        target=capture_stream,
        args=(WIFI_CAMERA_URL, "Phone-Camera"),
        daemon=True
    )
    axis_thread = threading.Thread(
        target=capture_stream,
        args=(AXIS_CAMERA_URL, "Axis-Camera"),
        daemon=True
    )

    mac_thread.start()
    phone_thread.start()
    axis_thread.start()

    mac_thread.join()
    phone_thread.join()
    axis_thread.join()
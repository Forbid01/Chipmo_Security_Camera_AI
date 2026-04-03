# app/services/camera_service.py

import cv2
import time
import queue
import threading
import app.core.state as state

WIFI_CAMERA_URL = "http://192.168.0.207:4747/video"
MAC_CAMERA_INDEX = 0


def capture_stream(source, camera_name):
    print(f" {camera_name} холбогдож байна: {source}")
    cap = cv2.VideoCapture(source)

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

            if camera_name == "Mac-Camera":
                # AI боловсруулаагүй бол камерын frame-г харуулна
                # AI боловсруулсан бол safe_update_display_queue давж бичнэ
                if state.latest_mac_frame is None:
                    state.latest_mac_frame = frame.copy()
                # ← УСТГАСАН: else байхгүй, AI-ийн frame-г дарахгүй
            else:
                # Phone камер AI-д ордоггүй тул үргэлж шинэчлэнэ
                state.latest_phone_frame = frame.copy()

            # AI queue руу үргэлж илгээнэ
            if not state.ai_input_queue.full():
                try:
                    state.ai_input_queue.put(frame.copy(), block=False)
                except queue.Full:
                    pass

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

    mac_thread.start()
    phone_thread.start()
    mac_thread.join()
import cv2
import time
import queue
import threading
import app.core.state as state  # State-ийг бүтнээр нь импортлов

# --- ТОХИРГОО ---
WIFI_CAMERA_URL = "http://192.168.0.207:4747/video"
MAC_CAMERA_INDEX = 0

def capture_stream(source, camera_name):
    """Камер бүрийг тусдаа урсгалаар унших функц"""
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
                state.latest_mac_frame = frame.copy()
            else:
                state.latest_phone_frame = frame.copy()

            # --- 2. AI МОДУЛЬ РУУ ИЛГЭЭХ ---
            if not state.ai_input_queue.full():
                try: 
                    state.ai_input_queue.put(frame.copy(), block=False)
                except queue.Full: 
                    pass

            # --- 3. BUFFER-Т ХАДГАЛАХ (Alert үүсгэх бичлэгт зориулж) ---
            with state.buffer_lock: 
                state.video_buffer.append(frame.copy())
                if len(state.video_buffer) > 200:
                    state.video_buffer.pop(0)
            
            # FPS хяналт (~30 FPS)
            time.sleep(0.02)

    except Exception as e:
        print(f" {camera_name} Exception: {e}")
    finally:
        cap.release()
        print(f" {camera_name} холболт хаагдлаа.")

def video_capture():
    """Mac болон Утасны камерыг зэрэг ажиллуулах үндсэн функц"""
    
    # Mac-ийн камерын урсгал
    mac_thread = threading.Thread(
        target=capture_stream, 
        args=(MAC_CAMERA_INDEX, "Mac-Camera"),
        daemon=True
    )
    
    # Утасны камерын урсгал
    phone_thread = threading.Thread(
        target=capture_stream, 
        args=(WIFI_CAMERA_URL, "Phone-Camera"),
        daemon=True
    )

    # Урсгалуудыг асаах
    mac_thread.start()
    phone_thread.start()

    # Үндсэн процесс дуусахаас сэргийлнэ
    mac_thread.join()

if __name__ == "__main__":
    video_capture()
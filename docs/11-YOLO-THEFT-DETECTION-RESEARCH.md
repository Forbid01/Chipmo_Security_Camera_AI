# YOLO-д суурилсан хулгайн илрүүлэлтийн AI систем — Судалгаа

> Огноо: 2026-04-21
> Эх сурвалж: GitHub trending, GitHub search, Ultralytics docs, ScienceDirect

---

## 1. Шилдэг Open Source Проектууд

### 1.1 vahapogut/Theft-Detection — Хамгийн бүрэн систем

- **GitHub:** https://github.com/vahapogut/Theft-Detection
- **Tech stack:** YOLOv8 + FastAPI + Next.js 14 + WebSocket + SQLite
- **Илрүүлэлтийн pipeline:**
  1. **Object Detection** — YOLOv8 nano (yolov8n.pt, yolov8n-pose.pt) → хүн, барааг илрүүлэх
  2. **Behavioral Analysis** — гар халаасанд хийх гэх мэт хөдөлгөөнийг хянах
  3. **Pose Estimation** — скелетон keypoint-аар сэжигтэй байрлал тодорхойлох
  4. **Face Recognition** — хар жагсаалт / VIP мэдээллийн сантай харьцуулах
- **Камер дэмжлэг:** USB болон IP камеруудыг WebSocket-ээр олноор нэгэн зэрэг
- **Дохиолол:** Dashboard (visual alert) + Telegram Bot + Email (SMTP)
- **Мэдээллийн сан:** SQLite — timestamp, alert type, confidence score хадгална
- **Шаардлага:** Python 3.9+, Node.js LTS, CUDA GPU (санал болгосон)

### 1.2 PhazerTech/yolo-rtsp-security-cam — RTSP камер + YOLO

- **GitHub:** https://github.com/PhazerTech/yolo-rtsp-security-cam
- **Онцлог:** 2 шатлалтай илрүүлэлт (Motion Detection → YOLO)
  - Хөдөлгөөн илэрсэн үед л YOLO ажиллана → CPU/GPU хэмнэлттэй
  - RTSP протоколоор IP камертай холбогдоно
  - Тасарвал 5 секунд тутам автоматаар дахин холбогдоно
- **YOLO тохиргоо:**
  - `--stream` — RTSP хаяг
  - `--yolo` — COCO dataset-ийн объектуудаас сонгох (person, car гм)
  - `--model` — YOLOv8 nano/small/medium
- **Motion detection параметрүүд:**
  - `threshold` — пикселийн өөрчлөлтийн босго (default: 350)
  - `start_frames` — бичлэг эхлүүлэх дараалсан frame тоо (default: 3)
  - `tail_length` — хөдөлгөөнгүй болсны дараах хүлээлт (default: 8 сек)
- **Давуу тал:** Raspberry Pi 4 дээр ч ажиллах боломжтой (motion-only mode)

### 1.3 Laoode/Theft_Detection — YOLOv5 + ROI + Alarm

- **GitHub:** https://github.com/Laoode/Theft_Detection
- **Tech stack:** YOLOv5 + OpenCV + Python
- **Архитектур:**
  - CCTV дүрс дээр ROI (Region of Interest) тодорхойлно
  - Тухайн хэсэгт хүн илэрвэл дохиолол өгнө
  - Зургийг хадгалж нотлох баримт болгоно
- **Бүтэц:** `main.py`, `Alarm/`, `Images/`, `Test Videos/`

### 1.4 alich03/Shoplifting-Detection-using-yolov8

- **GitHub:** https://github.com/alich03/Shoplifting-Detection-using-yolov8
- YOLOv8 ашиглан дэлгүүрийн хулгайг илрүүлэх

### 1.5 Jack-cky/SupermarketScanner

- **GitHub:** https://github.com/Jack-cky/SupermarketScanner
- Self-checkout дээрх хулгайг AI камерийн тусламжтай илрүүлэх

### 1.6 omerkhanjadoon/Yolo-Object-Recognition-Implementation-for-thief-alert-system

- **GitHub:** https://github.com/omerkhanjadoon/Yolo-Object-Recognition-Implementation-for-thief-alert-system
- Real-time хүн илрүүлж, дохиолол өгөх систем

---

## 2. Ultralytics YOLO26 — Хамгийн сүүлийн үеийн шийдэл

### 2.1 YOLO26 тухай

- **Гарсан огноо:** 2026-01-14
- **Docs:** https://docs.ultralytics.com/models/yolo26/
- **GitHub:** https://github.com/ultralytics/ultralytics (56,215+ stars)
- **Онцлог:**
  - Edge болон бага чадлын төхөөрөмжид зориулсан
  - NMS-free архитектур → илүү хурдан, хөнгөн
  - Object detection, tracking, instance segmentation дэмжинэ

### 2.2 Ultralytics Security Alarm System (Built-in шийдэл)

- **Guide:** https://github.com/ultralytics/ultralytics/blob/main/docs/en/guides/security-alarm-system.md

**Python код жишээ:**

```python
from ultralytics import solutions
import cv2

cap = cv2.VideoCapture("rtsp://camera_ip/stream")  # Камерын stream

alarm = solutions.SecurityAlarm(
    show=True,
    model="yolo26n.pt",
    records=1  # 1 илрүүлэлт = дохиолол
)
alarm.authenticate("from@email.com", "app_password", "to@email.com")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break
    results = alarm(frame)
```

**CLI хэрэглээ:**

```bash
yolo solutions security source="video.mp4" show=True
```

**Тохируулах параметрүүд:**

| Параметр | Төрөл | Default | Зорилго |
|----------|--------|---------|---------|
| `model` | string | None | YOLO model файлын зам |
| `records` | int | 5 | Дохиолол өгөх илрүүлэлтийн тоо |
| `conf` | float | 0.1 | Confidence threshold |
| `iou` | float | 0.7 | IoU шүүлтүүр |
| `tracker` | string | botsort.yaml | Tracking алгоритм |
| `device` | string | None | CPU/GPU сонголт |

---

## 3. Эрдэм шинжилгээний нийтлэл

**"Real-time theft detection in urban surveillance: A comparative analysis of YOLO-based approach"**
- **Эх сурвалж:** https://www.sciencedirect.com/science/article/pii/S2307187725010375
- YOLOv8-д суурилсан urban surveillance систем
- Тээврийн хэрэгслийн хулгай илрүүлэлт:
  - Нуусан улсын дугаартай: **98%** нарийвчлал
  - Харагдах улсын дугаартай: **99%** нарийвчлал
- License plate recognition модультай интеграц
- Web-based alert interface

---

## 4. Санал болгож буй архитектур

Дээрх судалгаанаас харахад хамгийн оновчтой хослол:

```
┌─────────────┐    RTSP/USB     ┌──────────────────┐
│  IP Camera   │──────────────▶│  Motion Detector  │
│  (CCTV)      │                │  (OpenCV)         │
└─────────────┘                └────────┬─────────┘
                                        │ motion detected
                                        ▼
                               ┌──────────────────┐
                               │  YOLO26 Detection │
                               │  (Person, Object) │
                               └────────┬─────────┘
                                        │ threat detected
                                        ▼
                               ┌──────────────────┐
                               │  Pose Estimation  │
                               │  (Suspicious act) │
                               └────────┬─────────┘
                                        │
                          ┌─────────────┼─────────────┐
                          ▼             ▼             ▼
                    ┌──────────┐ ┌──────────┐ ┌──────────┐
                    │ Telegram │ │  Email   │ │Dashboard │
                    │  Alert   │ │  Alert   │ │ (Web UI) │
                    └──────────┘ └──────────┘ └──────────┘
```

### Гол зарчмууд

1. **Motion Detection first** — CPU хэмнэлт (PhazerTech-ийн арга). Бүх frame-д YOLO ажиллуулахгүй, зөвхөн хөдөлгөөн илэрсэн үед.
2. **YOLO26n** — Хамгийн хурдан, edge-д тохиромжтой nano model
3. **Pose Estimation** — Сэжигтэй хөдөлгөөнийг илрүүлэх (vahapogut-ийн арга)
4. **Multi-channel alert** — Telegram + Email + Dashboard
5. **FastAPI + WebSocket** — Real-time dashboard, олон камерийн дэмжлэг

### Технологийн сонголт

| Давхарга | Технологи | Шалтгаан |
|----------|-----------|----------|
| Detection | YOLO26n + Pose | Хурдан, нарийвчлалтай, edge-д тохирно |
| Backend | FastAPI | Async, WebSocket дэмжлэг, хурдан |
| Frontend | Next.js / React | Real-time dashboard |
| Камер холболт | RTSP / USB | Стандарт IP камеруудтай нийцтэй |
| Мэдээллийн сан | SQLite / PostgreSQL | Event log, face database |
| Дохиолол | Telegram Bot API | Шуурхай, mobile-д тохиромжтой |
| GPU | CUDA (NVIDIA) | Inference хурдасгах |

---

## 5. Дүгнэлт

- **vahapogut/Theft-Detection** нь хамгийн бүрэн, production-д ойрхон систем (YOLOv8 + Pose + Face Recognition + Dashboard + Telegram)
- **PhazerTech/yolo-rtsp-security-cam** нь RTSP камерийн интеграцийн хамгийн сайн жишээ (motion-first арга)
- **Ultralytics YOLO26** нь хамгийн шинэ, албан ёсны шийдлүүдтэй (SecurityAlarm solution)
- Motion Detection → YOLO → Pose Estimation гэсэн шатлалтай арга нь CPU/GPU-ийн хэрэглээг бууруулж, нарийвчлалыг нэмэгдүүлнэ

---

## 6. Лицензийн шинжилгээ — Ашиглаж болох уу?

> Огноо: 2026-04-21
> Зорилго: Дээрх проектуудыг Chipmo төсөлдөө ашиглах боломжийг хууль ёсны талаас шалгах

### 6.1 Лицензийн хураангуй

| # | Repo | Лиценз | Үнэгүй хэрэглээ | Арилжааны зорилго | Chipmo-д ашиглах |
|---|------|--------|------------------|-------------------|------------------|
| 1 | vahapogut/Theft-Detection | **MIT** | Тийм | Тийм | **Болно** |
| 2 | PhazerTech/yolo-rtsp-security-cam | **AGPL-3.0** | Тийм | Бүх кодоо нээх шаардлагатай | **Эрсдэлтэй** |
| 3 | Laoode/Theft_Detection | **Байхгүй** | Болохгүй | Болохгүй | **Болохгүй** |
| 4 | alich03/Shoplifting-Detection | **Байхгүй** | Болохгүй | Болохгүй | **Болохгүй** |
| 5 | Jack-cky/SupermarketScanner | **MIT** | Тийм | Тийм | **Болно** |
| 6 | ultralytics/ultralytics | **AGPL-3.0 / Enterprise** | AGPL нөхцөлтэй | Төлбөртэй лиценз | **Доор тайлбарлав** |

### 6.2 Лицензийн төрлүүдийн тайлбар

#### MIT License (Хамгийн чөлөөтэй)
- Код хуулах, өөрчлөх, тараах, арилжааны зорилгоор ашиглах — **бүгд зөвшөөрөгдсөн**
- Ганц шаардлага: copyright notice болон лицензийн текстийг хадгалах
- **vahapogut/Theft-Detection** болон **Jack-cky/SupermarketScanner** нь MIT

#### AGPL-3.0 (Хамгийн хатуу copyleft)
- Код ашиглавал таны **бүх програмын кодыг** AGPL-3.0 лицензтэйгээр нээлттэй болгох ёстой
- SaaS/cloud хэлбэрээр үйлчилгээ үзүүлсэн ч мөн адил хамаарна ("SaaS loophole" хаасан)
- **PhazerTech/yolo-rtsp-security-cam** нь AGPL-3.0

#### Лицензгүй (All Rights Reserved)
- Хууль ёсоор зохиогч бүх эрхийг эзэмшинэ
- Хуулах, өөрчлөх, тараах — **бүгд хориотой**
- Зохиогчоос тусгай зөвшөөрөл авах шаардлагатай
- **Laoode/Theft_Detection** болон **alich03/Shoplifting-Detection** нь лицензгүй

### 6.3 Ultralytics YOLO — Хамгийн чухал анхааруулга

Ultralytics нь **хоёр лицензтэй (dual license):**

| Хувилбар | Нөхцөл | Chipmo-д хамаарах |
|----------|--------|-------------------|
| **AGPL-3.0** (үнэгүй) | Chipmo-ийн бүх кодыг нээлттэй болгох ёстой | Хэрэв open source төсөл бол зөвшөөрнө |
| **Enterprise License** (төлбөртэй) | Кодоо хаалттай байлгаж болно | Арилжааны бүтээгдэхүүн бол **энийг авах хэрэгтэй** |

> **Чухал:** MIT лицензтэй repo-ууд (vahapogut, Jack-cky) ч гэсэн дотроо Ultralytics YOLO-г dependency болгон ашигладаг. Тиймээс wrapper код нь MIT байсан ч, YOLO model өөрөө AGPL-3.0 хамаарна.

### 6.4 Chipmo төслийн хувьд зөвлөмж

#### Хувилбар A: Арилжааны бүтээгдэхүүн (Recommended)

1. **MIT repo-уудын код/архитектур** авч ашиглах → **Болно**
   - vahapogut/Theft-Detection — dashboard, alert system, pipeline архитектур
   - Jack-cky/SupermarketScanner — checkout detection логик
   - Copyright notice хадгалах л хэрэгтэй
2. **Ultralytics Enterprise License** худалдаж авах
   - https://www.ultralytics.com/license
   - Chipmo одоо YOLO11 ашиглаж байгаа тул аль хэдийн хамаарна
3. **Лицензгүй repo-уудаас** зөвхөн **санаа, арга барил** авах → **Болно** (санаа нь лицензгүй)
   - Код шууд хуулахгүй, өөрөө бичих

#### Хувилбар B: Open Source (AGPL-3.0 дагах)

1. Chipmo-ийн **бүх кодыг** AGPL-3.0 лицензтэйгээр нийтлэх
2. Бүх repo-уудыг чөлөөтэй ашиглах боломжтой болно
3. Гэхдээ хэрэглэгчид ч таны кодыг чөлөөтэй хуулж ашиглах эрхтэй болно

#### Хувилбар C: Хослуулсан арга

1. Core AI engine-ийг open source (AGPL-3.0) болгох
2. Dashboard, бизнес логик, multi-tenant системийг хаалттай байлгах
3. Dual license загварыг Ultralytics шиг өөрөө хэрэглэх

### 6.5 Одоо юу хийх вэ?

Chipmo төсөл одоо **YOLO11 (Ultralytics)** ашиглаж байгаа тул:
- Аль хэдийн AGPL-3.0 нөхцөл хамаарч байна
- Арилжааны бүтээгдэхүүн болгох бол Enterprise License авах шаардлагатай
- MIT лицензтэй repo-уудын кодыг чөлөөтэй reference болгон ашиглаж болно

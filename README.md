# Chipmo Security Camera AI

> AI-д суурилсан дэлгүүрийн хулгай илрүүлэх систем. Таны одоо байгаа хяналтын камеруудыг ухаалаг хулгай илрүүлэгч болгоно.

---

## Бизнесийн зорилго

Монголын жижиглэн худалдааны салбарт жил бүр тэрбум төгрөгийн бараа хулгайд алддаг. Ихэнх дэлгүүр эзэд өндөр үнэтэй хамгаалалтын систем суулгах боломжгүй. **Chipmo** нь одоо байгаа камеруудыг AI-р ухаалаг болгож, хулгайн алдагдлыг дунджаар **60%**-иар бууруулна.

### Үндсэн давуу тал

- **Нэмэлт төхөөрөмж шаардлагагүй** — Одоо байгаа IP камертай шууд ажиллана
- **Бодит цагийн илрүүлэлт** — Сэжигтэй үйлдэл илэрмэгц 3 секундэд мэдэгдэл
- **Telegram мэдэгдэл** — Зурагтай мэдэгдэл шууд утсанд
- **Өөрөө суралцдаг AI** — Хэрэглэх тусам илүү нарийвчлалтай
- **Олон салбар дэмжинэ** — Нэг самбараас бүх салбараа удирдах

---

## Технологи

| Давхарга | Технологи |
|----------|-----------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic |
| **Frontend** | React 19, Vite 8, TailwindCSS v4, Framer Motion |
| **Database** | PostgreSQL 15 (asyncpg) |
| **AI/ML** | YOLO11 (Ultralytics), PyTorch, Auto-learning |
| **Cache** | Redis |
| **Deployment** | Docker Compose, GitHub Actions CI/CD |
| **Мэдэгдэл** | Telegram Bot API, Gmail SMTP, Browser Push |

---

## Архитектур

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (React 19)               │
│   Landing │ Dashboard │ Admin Panel │ Settings       │
│   PWA │ Mobile Responsive │ Real-time Updates        │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS / JWT
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI Backend                      │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ Auth API │  │ Store API │  │ Camera/Video API │  │
│  └──────────┘  └───────────┘  └──────────────────┘  │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │Alert API │  │Feedback   │  │ Telegram API     │  │
│  └──────────┘  └───────────┘  └──────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │            Background Services                 │  │
│  │  AI Inference │ Alert Worker │ Auto-Learner    │  │
│  │  Camera Manager │ Telegram Notifier            │  │
│  └────────────────────────────────────────────────┘  │
└──────────┬───────────────────────────┬───────────────┘
           │                           │
    ┌──────▼──────┐            ┌───────▼───────┐
    │ PostgreSQL  │            │  YOLO11 Model │
    │   (async)   │            │  (Pose + Det) │
    └─────────────┘            └───────────────┘
```

---

## Multi-tenant бүтэц

```
Organization (Байгууллага)
  ├── Users (Хэрэглэгчид: user / admin / super_admin)
  ├── Stores (Дэлгүүрүүд / Салбарууд)
  │   ├── Cameras (Камерууд)
  │   │   └── Alerts (Сэрэмжлүүлэг)
  │   ├── Telegram chat_id (Мэдэгдлийн тохиргоо)
  │   └── ModelVersion (AI суралцсан тохиргоо)
```

---

## Суулгалт

### Шаардлага

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis (заавал биш)

### Backend

```bash
git clone https://github.com/Forbid01/Chipmo_Security_Camera_AI.git
cd Chipmo_Security_Camera_AI

# Python орчин
pip install -r requirements.txt

# .env тохируулах
cp .env.example .env
# .env файлыг засна: DATABASE_URL, SECRET_KEY, TELEGRAM_TOKEN

# Database
alembic upgrade head

# Эхлүүлэх
python shoplift_detector/main.py
```

### Frontend

```bash
cd security-web
npm install
npm run dev        # Development (http://localhost:5173)
npm run build      # Production build
```

### Docker

```bash
docker-compose up -d                    # Production
docker-compose -f docker-compose.yml \
  -f docker-compose.dev.yml up          # Development
```

---

## AI хулгай илрүүлэх систем

### Ажиллах зарчим

1. **Камераас зураг авах** — RTSP/MJPEG/USB камераас бодит цагийн зураг
2. **YOLO11 Pose Detection** — Хүний биеийн цэгүүдийг (keypoints) тодорхойлох
3. **Зан үйлийн шинжилгээ** — 6 төрлийн сэжигтэй үйлдлийг шалгах:
   - `looking_around` — Эргэн тойрноо харах (жин: 1.5)
   - `item_pickup` — Бараа авах хөдөлгөөн (жин: 15.0)
   - `body_block` — Камераас далдлах (жин: 3.0)
   - `crouch` — Бүдүүвчлэн суух (жин: 1.0)
   - `wrist_to_torso` — Бараа нуух (жин: 5.0)
   - `rapid_movement` — Шуурхай хөдөлгөөн (жин: 1.5)
4. **Оноо тооцоолол** — 150 фрэймийн турш хуримтлагдсан оноо (0.98 decay)
5. **Сэрэмжлүүлэг** — Оноо босго давбал зураг + Telegram мэдэгдэл илгээх
6. **Cooldown** — Давтагдсан мэдэгдэл гаргахгүй (15 сек)

### Auto-Learning (Өөрөө суралцах)

1. Ажилтан alert-д "Зөв" / "Буруу" гэж тэмдэглэнэ
2. 20+ feedback цуглармагц систем автоматаар:
   - Дэлгүүр бүрийн оновчтой босго тооцоолно
   - Оноон жинг тохируулна
   - Нарийвчлалын статистик хадгална
3. 5 минут тутам background-д ажиллана
4. Дэлгүүр бүрт тусдаа AI тохиргоо

---

## API бүтэц

### Нэвтрэлт (`/api/v1/auth`)
| Method | Endpoint | Тайлбар |
|--------|----------|---------|
| POST | `/auth/register` | Шинэ хэрэглэгч бүртгэх |
| POST | `/auth/token` | Нэвтрэх (JWT token авах) |
| GET | `/auth/me` | Өөрийн мэдээлэл |
| POST | `/auth/forgot-password` | Нууц үг сэргээх |
| POST | `/auth/verify-code` | OTP код баталгаажуулах |
| POST | `/auth/reset-password` | Шинэ нууц үг тохируулах |

### Дэлгүүр & Камер
| Method | Endpoint | Тайлбар |
|--------|----------|---------|
| GET | `/api/v1/my/cameras` | Миний камерууд |
| GET | `/api/v1/my/cameras/stores` | Миний дэлгүүрүүд |
| POST | `/api/v1/my/cameras` | Камер нэмэх |
| GET | `/api/v1/stores` | Бүх дэлгүүр |
| POST | `/api/v1/stores` | Дэлгүүр нэмэх |

### Видео & Сэрэмжлүүлэг
| Method | Endpoint | Тайлбар |
|--------|----------|---------|
| GET | `/api/v1/video/feed/{camera_id}` | Live MJPEG stream |
| GET | `/api/v1/video/store/{store_id}` | Дэлгүүрийн 4 камер grid |
| GET | `/api/v1/alerts` | Сэрэмжлүүлэг жагсаалт |
| POST | `/api/v1/feedback` | AI feedback (зөв/буруу) |

### Telegram мэдэгдэл
| Method | Endpoint | Тайлбар |
|--------|----------|---------|
| POST | `/api/v1/telegram/setup` | Chat ID бүртгэх |
| POST | `/api/v1/telegram/test` | Тест мэдэгдэл илгээх |
| DELETE | `/api/v1/telegram/{store_id}` | Мэдэгдэл унтраах |

### Админ (`/api/v1/admin` — super_admin эрхтэй)
| Method | Endpoint | Тайлбар |
|--------|----------|---------|
| GET | `/admin/stats` | Системийн статистик |
| GET/POST/DELETE | `/admin/organizations` | Байгууллага CRUD |
| GET/PUT/DELETE | `/admin/users` | Хэрэглэгч удирдлага |
| GET/POST/PUT/DELETE | `/admin/cameras` | Камер удирдлага |

---

## Frontend хуудсууд

| Хуудас | Зам | Тайлбар |
|--------|-----|---------|
| Landing | `/` | Маркетинг хуудас (үнэ, сэтгэгдэл, FAQ) |
| Login | `/login` | Нэвтрэх |
| Register | `/register` | Бүртгүүлэх (байгууллагын нэртэй) |
| Dashboard | `/dashboard` | Үндсэн самбар (видео, chart, alert) |
| Stores | `/stores` | Дэлгүүр удирдлага (CRUD) |
| Cameras | `/cameras` | Камер удирдлага (CRUD) |
| Settings | `/settings` | Профайл, Telegram тохиргоо |
| Admin | `/admin/control` | Super admin самбар |
| 404 | `*` | Хуудас олдсонгүй |

### Dashboard онцлог

- **Mobile responsive** — Hamburger menu, sidebar overlay
- **Browser push notification** — Шинэ alert ирэхэд notification
- **Camera status** — Online/offline тэмдэглэл
- **CSV export** — Сэрэмжлүүлгийг файлаар татах
- **Alert detail modal** — Том зураг + AI feedback
- **Store filter** — Дэлгүүрээр шүүсэн alert
- **Onboarding guide** — Шинэ хэрэглэгчид алхамтай зааварчилгаа

---

## Аюулгүй байдал

- **JWT Bearer Token** + httpOnly Cookie
- **bcrypt** нууц үг хэшлэлт (uppercase + lowercase + digit + special char)
- **Rate limiting** — Нэвтрэлт: 10/мин, Нууц үг сэргээх: 5/мин
- **CORS** тохиргоо
- **Security headers**: X-Frame-Options, CSP, HSTS, XSS-Protection
- **Role-based access**: user → admin → super_admin

---

## CI/CD

GitHub Actions (`ci.yml`):
1. **Lint** — ruff + mypy
2. **Test** — pytest + coverage (PostgreSQL test DB)
3. **Build** — Docker image (buildx + cache)

---

## Тушаалууд

```bash
# Backend
python shoplift_detector/main.py        # Сервер эхлүүлэх
pytest --cov=shoplift_detector tests/   # Тест
ruff check shoplift_detector/           # Lint
alembic upgrade head                    # Migration

# Frontend
cd security-web
npm run dev                             # Dev server
npm run build                           # Production build
npm run lint                            # ESLint

# Docker
docker-compose up -d                    # Production
docker-compose logs -f app              # Лог харах
```

---

## Зохиогч

- **Chipmo LLC** — Улаанбаатар, Монгол
- **Утас:** +976 8810-8766
- **Имэйл:** info@chipmo.mn
- **GitHub:** [Forbid01/Chipmo_Security_Camera_AI](https://github.com/Forbid01/Chipmo_Security_Camera_AI)

---

## Лиценз

Энэхүү програм хангамж нь Chipmo LLC-ийн өмч бөгөөд зөвшөөрөлгүйгээр хуулбарлах, тараах, ашиглахыг хориглоно.

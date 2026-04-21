# 00 — AS-IS Inventory

Одоогийн repo-ийн бодит implementation inventory. Энэ document нь roadmap/spec
баримтуудаас ялгаатай: зөвхөн одоо codebase-д байгаа endpoint, table, service,
environment variable, deployment assumption-уудыг тэмдэглэнэ.

Updated: 2026-04-20

---

## Runtime

| Хэсэг | Одоогийн байдал |
|---|---|
| Python runtime | `python-3.11.10` (`runtime.txt`, Docker `python:3.11-slim`) |
| Backend | FastAPI app: `shoplift_detector.main:app` |
| Frontend | React 19 + Vite app in `security-web/`; build output copied to `shoplift_detector/dist/` |
| Database | PostgreSQL via SQLAlchemy async + Alembic |
| Test baseline | `python3.12 -m pytest -q` passes locally; target runtime remains Python 3.11 |
| Lint baseline | `python3.12 -m ruff check .`, `cd security-web && npm run lint` pass |
| Docker local status | Dockerfile exists, but local machine currently has no `docker` CLI available |

---

## Current Backend Entrypoint

- Main app: `shoplift_detector/main.py`
- API v1 router: `shoplift_detector/app/api/v1/__init__.py`
- Legacy compatibility endpoints are still mounted directly in `shoplift_detector/main.py`
- SPA fallback serves `shoplift_detector/dist/` when frontend build exists

Startup behavior:

- Creates DB tables with `Base.metadata.create_all`
- Loads active cameras from DB into `camera_manager`
- Configures Telegram notifier from `TELEGRAM_TOKEN`
- Starts background threads:
  - `alert_worker`
  - `ai_inference`
- Starts async auto-learning task on the main event loop

---

## Current API Endpoints

### Health / Legacy Root

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | App, version, camera counts, DB status |
| POST | `/token` | Legacy login, sets auth cookie |
| GET | `/users/me` | Legacy current user profile |
| POST | `/register` | Legacy registration |
| GET | `/alerts` | Legacy latest alerts |
| GET | `/video_feed` | Legacy MJPEG stream |
| GET | `/video_feed/{camera_id}` | Legacy MJPEG stream for `mac`, `phone`, `axis` |
| POST | `/api/contact` | Contact email |
| POST | `/forgot-password` | Legacy password recovery |
| POST | `/verify-code` | Legacy recovery code verify |
| POST | `/reset-password` | Legacy password reset |

### `/api/v1/auth`

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/auth/register` | User registration |
| POST | `/api/v1/auth/token` | OAuth2 form login |
| POST | `/api/v1/auth/logout` | Clear auth cookie |
| GET | `/api/v1/auth/me` | Current user profile |
| POST | `/api/v1/auth/forgot-password` | Recovery OTP |
| POST | `/api/v1/auth/verify-code` | Verify OTP |
| POST | `/api/v1/auth/reset-password` | Reset password |

### `/api/v1/admin`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/admin/organizations` | Super admin |
| POST | `/api/v1/admin/organizations` | Super admin |
| DELETE | `/api/v1/admin/organizations/{org_id}` | Super admin |
| GET | `/api/v1/admin/users` | Super admin |
| PUT | `/api/v1/admin/users/{user_id}/role` | Super admin |
| PUT | `/api/v1/admin/users/{user_id}/organization` | Super admin |
| DELETE | `/api/v1/admin/users/{user_id}` | Super admin |
| GET | `/api/v1/admin/stats` | Super admin |

Legacy admin aliases also exist under `/admin/...`.

### Cameras / Stores / Alerts / Feedback

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/cameras` | Admin camera list |
| POST | `/api/v1/cameras` | Admin camera create |
| PUT | `/api/v1/cameras/{camera_id}` | Admin camera update |
| DELETE | `/api/v1/cameras/{camera_id}` | Admin camera delete |
| GET | `/api/v1/cameras/status` | Camera manager runtime status |
| GET | `/api/v1/stores` | Store list |
| POST | `/api/v1/stores` | Super admin create |
| GET | `/api/v1/stores/{store_id}` | Store detail |
| PUT | `/api/v1/stores/{store_id}` | Store update |
| DELETE | `/api/v1/stores/{store_id}` | Store delete |
| GET | `/api/v1/my/cameras` | User-scoped cameras |
| POST | `/api/v1/my/cameras` | User-scoped camera create |
| PUT | `/api/v1/my/cameras/{camera_id}` | User-scoped camera update |
| DELETE | `/api/v1/my/cameras/{camera_id}` | User-scoped camera delete |
| GET | `/api/v1/my/cameras/stores` | User-scoped stores |
| POST | `/api/v1/my/cameras/stores` | User-scoped store create |
| PUT | `/api/v1/my/cameras/stores/{store_id}` | User-scoped store update |
| DELETE | `/api/v1/my/cameras/stores/{store_id}` | User-scoped store delete |
| GET | `/api/v1/alerts` | Latest alerts |
| GET | `/api/v1/alerts/admin` | Admin alert list |
| PUT | `/api/v1/alerts/{alert_id}/reviewed` | Mark reviewed |
| DELETE | `/api/v1/alerts/{alert_id}` | Delete alert |
| POST | `/api/v1/feedback` | Alert feedback |
| GET | `/api/v1/feedback/stats` | Feedback stats |
| GET | `/api/v1/feedback/learning-status` | Auto-learning status |

### Video / Telegram / Pricing

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/video/feed/{camera_id}` | Authenticated MJPEG stream |
| GET | `/api/v1/video/store/{store_id}` | Store grid MJPEG stream |
| POST | `/api/v1/telegram/setup` | Store Telegram chat setup |
| POST | `/api/v1/telegram/test` | Test Telegram notification |
| DELETE | `/api/v1/telegram/{store_id}` | Remove store Telegram chat |
| GET | `/api/v1/pricing/quote` | Pricing quote |

---

## Current Database Tables

Source: `shoplift_detector/app/db/models/`.

| Table | Model | Key columns / notes |
|---|---|---|
| `organizations` | `Organization` | `id`, `name`, timestamps |
| `users` | `User` | `id`, `username`, `email`, `phone_number`, `hashed_password`, `role`, `organization_id`, recovery fields, `is_active` |
| `stores` | `Store` | `id`, `name`, `address`, `organization_id`, `alert_threshold`, `alert_cooldown`, `telegram_chat_id` |
| `cameras` | `Camera` | `id`, `name`, `url`, `camera_type`, `store_id`, `organization_id`, `is_active`, `is_ai_enabled` |
| `alerts` | `Alert` | `id`, `person_id`, `organization_id`, `store_id`, `camera_id`, `event_time`, `image_path`, `video_path`, `description`, `confidence_score`, `reviewed`, `feedback_status` |
| `alert_feedback` | `AlertFeedback` | `id`, `alert_id`, `store_id`, `feedback_type`, `reviewer_id`, `notes`, `score_at_alert`, `behaviors_detected`, `created_at` |
| `model_versions` | `ModelVersion` | `id`, `store_id`, `version`, `model_type`, metrics, `learned_threshold`, `learned_score_weights`, `total_feedback_used`, `is_active`, `trained_at` |
| `alert_state` | `AlertStateRecord` | `id`, `camera_id`, `person_track_id`, `state`, `last_alert_id`, `last_alert_at`, `cooldown_until`, `resolved_at` |
| `camera_health` | `CameraHealth` | `camera_id`, `store_id`, `status`, `is_connected`, `fps`, `last_frame_at`, `last_heartbeat_at`, `offline_since`, `last_error`, `last_notification_at` |
| `cases` | `CaseRecord` | `id`, `alert_id`, `store_id`, `camera_id`, `timestamp`, `behavior_scores`, `clip_path`, `keyframe_paths`, label fields, VLM fields, `qdrant_point_id` |

Current schema uses integer primary keys for the core tables above. There is no
current `alert_events` table, no `edge_boxes`, no `sync_packs`, no
`audit_log`, and no TimescaleDB hypertables yet.

---

## Current Services

| Service / module | Current responsibility |
|---|---|
| `app/services/ai_service.py` | YOLO pose/object inference, rule-based behavior score, alert save/Telegram trigger |
| `app/services/camera_manager.py` | Runtime camera registration, OpenCV capture loops, reconnect backoff, AI queue |
| `app/services/alert_service.py` | Legacy alert queue worker, Telegram photo/video sending |
| `app/services/telegram_notifier.py` | Store-specific Telegram notification helper |
| `app/services/auto_learner.py` | Feedback-based threshold and weight tuning; writes `model_versions` |
| `app/services/storage.py` | Local / Cloudinary / S3 alert image storage abstraction |
| `app/services/alert_manager.py` | Alert dedup state machine backed by `alert_state` |
| `app/services/clip_retention.py` | Local media retention cleanup: normal 48h, alert 30d, labeled unlimited |
| `app/services/email_service.py` | Contact and OTP email sending |
| `app/services/auth_service.py` | Legacy auth helper |
| `app/services/pricing_service.py` | Pricing quote calculations |
| `app/services/camera_service.py` | Camera-related helper service |

Current AI pipeline:

- `camera_manager` reads frames and pushes sampled frames to a bounded AI queue.
- `ai_service` runs YOLO pose tracking and object detection.
- Six behavior signals contribute to score:
  - `looking_around`
  - `item_pickup`
  - `body_block`
  - `crouch`
  - `wrist_to_torso`
  - `rapid_movement`
- Alert cooldown is currently in memory (`last_alert_time`) plus repository-level duplicate guard.
- There is no DB-backed alert state machine yet.

---

## Environment Variables

Source: `shoplift_detector/app/core/config.py`.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | yes | - | JWT signing key |
| `ALGORITHM` | no | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `1440` | Token/cookie lifetime |
| `DATABASE_URL` | no | - | Preferred DB URL; supports `postgres://`, `postgresql://`, async conversion |
| `DB_NAME` | no | `postgres` | Used when `DATABASE_URL` absent |
| `DB_USER` | no | `postgres` | Used when `DATABASE_URL` absent |
| `DB_PASSWORD` | no | empty | Used when `DATABASE_URL` absent |
| `DB_HOST` | no | `127.0.0.1` | Used when `DATABASE_URL` absent |
| `DB_PORT` | no | `5432` | Used when `DATABASE_URL` absent |
| `TELEGRAM_TOKEN` | no | - | Required for Telegram notifications |
| `TELEGRAM_CHAT_ID` | no | - | Legacy global Telegram fallback |
| `ALLOWED_ORIGINS` | no | `*` | Comma-separated string accepted |
| `MAIL_USERNAME` | no | - | Required for email sending |
| `MAIL_PASSWORD` | no | - | Required for email sending |
| `MAIL_FROM` | no | - | Sender email |
| `WIFI_CAMERA_URL` | no | empty | Legacy default camera source |
| `AXIS_CAMERA_URL` | no | empty | Legacy default camera source |
| `MAC_CAMERA_INDEX` | no | `-1` | USB fallback disabled by default |
| `ENABLE_DEFAULT_CAMERAS` | no | `false` | Must stay false in headless deployment |
| `CAMERA_SOURCE` | no | empty | Optional single source override |
| `AI_SCORE_ALERT_TRIGGER` | no | `80.0` | Legacy/default score threshold |
| `AI_ALERT_COOLDOWN` | no | `60` | Legacy/default cooldown |
| `AI_AUTO_LEARN` | no | `true` | Enables feedback learning task |
| `AI_FRAME_SKIP` | no | `5` | Frame sampling for AI queue |
| `AI_INPUT_SIZE` | no | `640` | Resize target |
| `AI_QUEUE_MAXSIZE` | no | `8` | Bounded AI input queue |
| `RTSP_RECONNECT_BASE` | no | `1.0` | Initial reconnect delay |
| `RTSP_RECONNECT_MAX` | no | `60.0` | Max reconnect delay |
| `STORAGE_BACKEND` | no | `local` | `local`, `cloudinary`, or `s3` |
| `PUBLIC_BASE_URL` | no | empty | Public URL helper |
| `CLOUDINARY_URL` | no | - | Required for Cloudinary storage |
| `CLOUDINARY_FOLDER` | no | `chipmo/alerts` | Cloudinary path |
| `S3_BUCKET` | no | - | Required for S3 storage |
| `S3_REGION` | no | `us-east-1` | S3 region |
| `S3_PREFIX` | no | `alerts` | S3 key prefix |
| `S3_ENDPOINT_URL` | no | - | S3-compatible endpoint |
| `AWS_ACCESS_KEY_ID` | no | - | S3 credential |
| `AWS_SECRET_ACCESS_KEY` | no | - | S3 credential |
| `SENTRY_DSN` | no | - | Optional Sentry integration |
| `PORT` | no | `8000` | Server port |
| `DEBUG` | no | `false` | Debug mode; affects cookie secure flag |

---

## Deployment Assumptions

### Railway / Nixpacks

- `nixpacks.toml` installs Python 3.11 and Node 20.
- Build phase runs:
  - `pip install -r requirements.txt`
  - `cd security-web && npm ci`
  - `cd security-web && npm run build`
- Start command runs:
  - `alembic upgrade head`
  - `uvicorn shoplift_detector.main:app --host 0.0.0.0 --port ${PORT:-8000}`
- `Procfile` also contains `release: alembic upgrade head` and web uvicorn command.

### Docker

- Multi-stage build:
  - Python dependency builder
  - Node frontend builder
  - Python runtime image
- Runtime image installs `ffmpeg`, `libgl1`, `libglib2.0-0`, `libstdc++6`, `libpq-dev`.
- Healthcheck calls `http://localhost:8000/health`.
- Docker command runs Alembic then Uvicorn.

### Docker Compose

- Services:
  - `app`
  - `postgres`
  - `redis`
- Postgres image: `postgres:15-alpine`
- Redis image: `redis:7-alpine`
- `app` expects `.env` and overrides `DB_HOST=postgres`, `DB_PORT=5432`.

---

## Explicit Non-Goals In Current Code

These are target roadmap items, not current implementation:

- Edge box API (`/api/edge/*`)
- `edge_boxes`, `sync_packs`, `audit_log`, `inference_metrics`
- TimescaleDB hypertables and continuous aggregates
- Qdrant collections
- OSNet Re-ID
- CLIP case embeddings
- RAG suppression
- VLM verification
- Dynamic FPS controller module
- Batched inference engine
- TensorRT runtime
- Face blur / clip encryption
- Multi-channel notification dispatcher beyond Telegram/email helpers

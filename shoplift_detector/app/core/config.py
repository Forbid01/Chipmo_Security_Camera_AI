import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings

# Ultralytics writes per-user config to ~/.config/Ultralytics — not writable in
# Railway's read-only container home. Point it at /tmp before any ultralytics
# import touches the filesystem.
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp")


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Chipmo Security AI"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    PORT: int = 8000

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Database
    DATABASE_URL: str | None = None
    DB_NAME: str = "postgres"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432

    # TimescaleDB. See docs/spikes/timescaledb-integration.md — disabled on
    # Railway's managed Postgres, enabled on self-hosted central. When true,
    # the guarded migration converts eligible tables to hypertables.
    TIMESCALEDB_ENABLED: bool = False

    # Tenant isolation (T1-04). When true, the SQLAlchemy event hook
    # pins `app.current_tenant_id` per request and RLS policies enforce
    # per-row visibility. When false, the hook sets
    # `app.bypass_tenant='on'` at session start so legacy writers keep
    # working during the rollout window.
    TENANCY_RLS_ENFORCED: bool = False

    # Telegram
    TELEGRAM_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None

    # CORS
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Email
    MAIL_USERNAME: str | None = None
    MAIL_PASSWORD: str | None = None
    MAIL_FROM: str | None = None

    # Camera defaults — MAC index < 0 disables the local USB fallback,
    # which must stay off on headless servers (Railway has no /dev/video0).
    WIFI_CAMERA_URL: str = ""
    AXIS_CAMERA_URL: str = ""
    MAC_CAMERA_INDEX: int = -1
    ENABLE_DEFAULT_CAMERAS: bool = False
    # Optional single-source override. Accepts an RTSP/HTTP URL or a USB
    # index string ("0"). Empty = no default stream (headless-safe).
    CAMERA_SOURCE: str = ""

    # AI
    AI_SCORE_ALERT_TRIGGER: float = 80.0
    AI_ALERT_COOLDOWN: int = 60
    AI_AUTO_LEARN: bool = True
    AI_FRAME_SKIP: int = 5
    AI_INPUT_SIZE: int = 640
    AI_QUEUE_MAXSIZE: int = 8

    # RTSP reconnect
    RTSP_RECONNECT_BASE: float = 1.0
    RTSP_RECONNECT_MAX: float = 60.0

    # Camera health heartbeat/offline tracking
    CAMERA_HEALTH_HEARTBEAT_INTERVAL_SECONDS: float = 5.0
    CAMERA_HEALTH_OFFLINE_AFTER_SECONDS: float = 30.0
    CAMERA_HEALTH_NOTIFICATION_AFTER_SECONDS: float = 300.0

    # Local media retention. Labeled alert media is kept indefinitely.
    MEDIA_RETENTION_ENABLED: bool = True
    MEDIA_RETENTION_INTERVAL_SECONDS: float = 86400.0
    NORMAL_CLIP_RETENTION_HOURS: float = 48.0
    ALERT_CLIP_RETENTION_DAYS: float = 30.0

    # Storage backend: local | cloudinary | s3
    STORAGE_BACKEND: str = "local"
    PUBLIC_BASE_URL: str = ""
    CLOUDINARY_URL: str | None = None
    CLOUDINARY_FOLDER: str = "chipmo/alerts"
    S3_BUCKET: str | None = None
    S3_REGION: str = "us-east-1"
    S3_PREFIX: str = "alerts"
    S3_ENDPOINT_URL: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # Sentry
    SENTRY_DSN: str | None = None

    # Transactional email (Resend) — T2-02. When unset, the handler
    # wires a `RecordingEmailSender` so dev/staging signups still
    # work without live email delivery.
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "Sentry <no-reply@sentry.mn>"

    # Twilio SMS — T2-03. All three fields must be set for SMS OTP to
    # activate. Missing any falls through to email-only.
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_FROM_NUMBER: str | None = None

    # PostHog server-side capture (T2-09). Unset → events go to the
    # null recorder (no network I/O).
    POSTHOG_API_KEY: str | None = None
    POSTHOG_HOST: str = "https://app.posthog.com"

    # Live chat widget (T2-11). Unset → the onboarding pages do not
    # load the widget script.
    CRISP_WEBSITE_ID: str | None = None

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if "+asyncpg" in url:
                url = url.replace("+asyncpg", "")
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Backward compatibility
settings = get_settings()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALERTS_DIR = os.path.join(BASE_DIR, "alerts")
FACES_DIR = os.path.join(BASE_DIR, "faces")

for folder in [ALERTS_DIR, FACES_DIR]:
    os.makedirs(folder, exist_ok=True)

TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
TELEGRAM_CHAT_ID = settings.TELEGRAM_CHAT_ID
ALLOWED_ORIGINS = settings.ALLOWED_ORIGINS

DEFAULT_CAMERA_SOURCES = {
    "mac": settings.MAC_CAMERA_INDEX,
    "phone": settings.WIFI_CAMERA_URL,
    "axis": settings.AXIS_CAMERA_URL,
}

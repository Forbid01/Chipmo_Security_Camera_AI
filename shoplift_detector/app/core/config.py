import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings

# Ultralytics writes per-user config to ~/.config/Ultralytics — not writable in
# Railway's read-only container home. Point it at /tmp before any ultralytics
# import touches the filesystem.
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp")

# Same problem for the HuggingFace cache (used by sentence-transformers /
# transformers when RAG or VLM is enabled). The first model download
# would otherwise fail with PermissionError on Railway. /tmp persists for
# the container lifetime which is fine — the wheel is small enough that
# a cold-start re-download is acceptable.
os.environ.setdefault("HF_HOME", "/tmp/hf_cache")
os.environ.setdefault("TRANSFORMERS_CACHE", "/tmp/hf_cache")
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", "/tmp/hf_cache")


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

    # --- RAG / Embeddings ---------------------------------------------------
    # Multilingual e5 covers Mongolian + English store policy text. The
    # service module loads the model lazily on first use so unit tests
    # and tenants with RAG disabled don't pay the import cost.
    #
    # Vectors live inside Postgres via pgvector — no separate vector
    # service. The matching alembic migration installs the extension
    # and adds the embedding column.
    #
    # Default OFF: a fresh deploy without the migration applied would
    # otherwise raise on every alert. Flip to true *after* the
    # migration has run and the embedding model is reachable from the
    # deploy environment.
    RAG_ENABLED: bool = False
    RAG_MODEL_NAME: str = "intfloat/multilingual-e5-small"
    RAG_TOP_K: int = 5
    RAG_DEVICE: str = "cpu"  # "cuda" if available; embedding is cheap on CPU

    # --- Vision-Language Model (Qwen2.5-VL) ---------------------------------
    # Heavy GPU model — the service guards against missing CUDA and
    # short-circuits to a "not_run" verdict when VLM_ENABLED is False
    # so deployments without a GPU stay functional.
    #
    # Two execution modes (selected at runtime by VLM_REMOTE_URL):
    #
    #   - **Local**: VLM_REMOTE_URL is empty. transformers loads
    #     Qwen2.5-VL in-process. Requires CUDA on the same host as the
    #     main app. Used in dev / single-box deployments.
    #
    #   - **Remote**: VLM_REMOTE_URL points at a GPU host running the
    #     `vlm_server/` microservice. The main app posts the frame +
    #     description via HTTP and awaits a JSON verdict. This is the
    #     production pattern: keep the main API on a small CPU box
    #     (Railway, Fly, etc.) and put the heavy model on a dedicated
    #     GPU server you control.
    #
    # VLM_API_KEY authenticates the HTTP call between the two services
    # via a Bearer token. NEVER leave it empty in remote mode — without
    # auth the GPU endpoint is reachable by anyone who finds the URL.
    VLM_ENABLED: bool = False
    VLM_MODEL_NAME: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    VLM_DEVICE: str = "cuda"
    VLM_TIMEOUT_SECONDS: float = 30.0
    VLM_MAX_NEW_TOKENS: int = 256
    VLM_DTYPE: str = "bfloat16"  # "float16" on older GPUs

    # Remote VLM microservice. Empty string = local in-process mode.
    VLM_REMOTE_URL: str = ""
    VLM_API_KEY: str = ""

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

    # Installer asset CDN (T4-06). The `GET /installer/download`
    # endpoint signs a redirect to `{INSTALLER_BASE_URL}/{os}/...`.
    INSTALLER_BASE_URL: str = "https://downloads.sentry.mn"
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

    # FCM push notifications — T5-07. Unset → the escalation
    # dispatcher falls through to a recording (in-memory) sender.
    FCM_SERVER_KEY: str | None = None

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

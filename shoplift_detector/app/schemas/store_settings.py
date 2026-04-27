"""Store-level AI configuration schema.

Single source of truth for per-store behavior knobs: detection thresholds,
night-mode adjustments, dynamic FPS, RAG/VLM toggles, clip retention,
notification channels. Persisted as `stores.settings JSONB`.

Unknown keys are rejected so that typos in admin UI payloads fail loudly
rather than silently drifting from the documented contract.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TelegramChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_ids: list[str] = Field(default_factory=list)


class SmsChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numbers: list[str] = Field(default_factory=list)


class EmailChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    addresses: list[str] = Field(default_factory=list)


class NotificationChannels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram: TelegramChannel = Field(default_factory=TelegramChannel)
    sms: SmsChannel = Field(default_factory=SmsChannel)
    email: EmailChannel = Field(default_factory=EmailChannel)


class SeverityThresholdsSchema(BaseModel):
    """Per-store 4-level classifier breakpoints (T5-01).

    The AI scoring loop classifies each behavior score into
    green/yellow/orange/red using these thresholds. Defaults match the
    T5 spec (40/70/85). Any override must remain strictly increasing;
    the validator enforces that so a typo in the admin UI can't collapse
    two tiers into one.
    """

    model_config = ConfigDict(extra="forbid")

    yellow: float = Field(default=40.0, ge=0.0)
    orange: float = Field(default=70.0, ge=0.0)
    red: float = Field(default=85.0, ge=0.0)

    @model_validator(mode="after")
    def _strictly_increasing(self) -> "SeverityThresholdsSchema":
        if not (self.yellow < self.orange < self.red):
            raise ValueError(
                "severity thresholds must be strictly increasing "
                f"(yellow={self.yellow}, orange={self.orange}, red={self.red})"
            )
        return self

    def classify(self, score: float) -> str:
        """Delegate to the domain classifier so callers that hold a
        schema instance don't have to round-trip through
        `to_domain()`."""
        from app.core.severity import SeverityThresholds as _Domain

        return _Domain(
            yellow=self.yellow, orange=self.orange, red=self.red
        ).classify(score)


class StoreSettings(BaseModel):
    """Authoritative per-store AI config.

    Every field has a documented default so that missing keys in the DB
    JSONB payload still resolve to a stable config at runtime.
    """

    model_config = ConfigDict(extra="forbid")

    # Alert decision — legacy single threshold kept for backward
    # compatibility with the auto-learner's learned value. The 4-level
    # classifier (T5-01) below is the new primary signal; when both
    # are present the classifier wins.
    alert_threshold: float = Field(default=80.0, ge=0.0)
    alert_cooldown_seconds: int = Field(default=60, ge=0)

    # 4-level severity thresholds (T5-01). Store-level override of the
    # module defaults in app/core/severity.py.
    severity_thresholds: SeverityThresholdsSchema = Field(
        default_factory=SeverityThresholdsSchema
    )

    # Night mode
    night_mode_enabled: bool = True
    night_luminance_threshold: float = Field(default=60.0, ge=0.0, le=255.0)

    # Dynamic FPS
    dynamic_fps_enabled: bool = True
    fps_idle: int = Field(default=3, ge=1, le=60)
    fps_active: int = Field(default=15, ge=1, le=60)
    fps_suspicious: int = Field(default=30, ge=1, le=120)

    # Clip retention
    clip_retention_normal_h: int = Field(default=48, ge=1)
    clip_retention_alert_d: int = Field(default=30, ge=1)

    # Privacy
    face_blur_enabled: bool = True

    # RAG / VLM
    rag_check_enabled: bool = True
    rag_fp_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    vlm_verification_enabled: bool = True
    vlm_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    # Locale
    timezone: str = "Asia/Ulaanbaatar"

    # Notifications
    notification_channels: NotificationChannels = Field(
        default_factory=NotificationChannels
    )


class StoreSettingsPatch(BaseModel):
    """Partial update payload. Any unspecified field keeps its stored value.

    Unknown keys still raise, matching the full schema's strictness.
    """

    model_config = ConfigDict(extra="forbid")

    alert_threshold: float | None = Field(default=None, ge=0.0)
    alert_cooldown_seconds: int | None = Field(default=None, ge=0)
    severity_thresholds: SeverityThresholdsSchema | None = None
    night_mode_enabled: bool | None = None
    night_luminance_threshold: float | None = Field(default=None, ge=0.0, le=255.0)
    dynamic_fps_enabled: bool | None = None
    fps_idle: int | None = Field(default=None, ge=1, le=60)
    fps_active: int | None = Field(default=None, ge=1, le=60)
    fps_suspicious: int | None = Field(default=None, ge=1, le=120)
    clip_retention_normal_h: int | None = Field(default=None, ge=1)
    clip_retention_alert_d: int | None = Field(default=None, ge=1)
    face_blur_enabled: bool | None = None
    rag_check_enabled: bool | None = None
    rag_fp_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    vlm_verification_enabled: bool | None = None
    vlm_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    timezone: str | None = None
    notification_channels: NotificationChannels | None = None


def default_settings_payload() -> dict:
    """Baseline JSONB payload used for backfilling existing stores."""
    return StoreSettings().model_dump(mode="json")


def resolve_settings(stored: dict | None) -> StoreSettings:
    """Merge a possibly-partial stored payload with defaults.

    - None / empty → full defaults
    - Unknown keys in `stored` raise (loud failure)
    - Known missing keys fall back to defaults
    """
    if not stored:
        return StoreSettings()
    return StoreSettings.model_validate(stored)


ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(StoreSettings.model_fields.keys())

SettingsMergeStrategy = Literal["replace", "patch"]

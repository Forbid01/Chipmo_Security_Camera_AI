"""Tests for StoreSettings schema, repository, and API endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from shoplift_detector.app.schemas.store_settings import (
    StoreSettings,
    StoreSettingsPatch,
    default_settings_payload,
    resolve_settings,
)

# ---------------------------------------------------------------------------
# Schema behaviour
# ---------------------------------------------------------------------------

def test_default_settings_has_all_required_keys():
    settings = StoreSettings()
    expected = {
        "alert_threshold",
        "alert_cooldown_seconds",
        "night_mode_enabled",
        "night_luminance_threshold",
        "dynamic_fps_enabled",
        "fps_idle",
        "fps_active",
        "fps_suspicious",
        "clip_retention_normal_h",
        "clip_retention_alert_d",
        "face_blur_enabled",
        "rag_check_enabled",
        "rag_fp_threshold",
        "vlm_verification_enabled",
        "vlm_confidence_threshold",
        "timezone",
        "notification_channels",
        "severity_thresholds",
    }
    assert set(settings.model_dump().keys()) == expected


def test_unknown_keys_are_rejected():
    with pytest.raises(ValidationError):
        StoreSettings.model_validate({"unexpected_field": 123})


def test_unknown_keys_on_patch_are_rejected():
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate({"foo": "bar"})


def test_rag_fp_threshold_out_of_range_rejected():
    with pytest.raises(ValidationError):
        StoreSettings.model_validate({"rag_fp_threshold": 1.2})


def test_resolve_settings_fills_missing_keys_with_defaults():
    partial = {"alert_threshold": 42.0}
    resolved = resolve_settings(partial)
    assert resolved.alert_threshold == 42.0
    assert resolved.alert_cooldown_seconds == 60  # default
    assert resolved.night_mode_enabled is True


def test_resolve_settings_accepts_none_returns_defaults():
    resolved = resolve_settings(None)
    assert resolved == StoreSettings()


def test_nested_notification_channels_reject_unknown_keys():
    bad = {
        "notification_channels": {
            "telegram": {"chat_ids": ["123"], "foo": 1}
        }
    }
    with pytest.raises(ValidationError):
        StoreSettings.model_validate(bad)


def test_default_settings_payload_is_json_serializable():
    payload = default_settings_payload()
    import json
    json.dumps(payload)


# ---------------------------------------------------------------------------
# Repository: legacy fallback when settings column is missing
# ---------------------------------------------------------------------------

class _FakeMappingResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


class _FakeColumnCheckResult:
    def __init__(self, exists: bool):
        self.exists = exists

    def fetchone(self):
        return (1,) if self.exists else None


@pytest.mark.asyncio
async def test_get_settings_falls_back_to_legacy_columns_without_jsonb():
    from shoplift_detector.app.db.repository.stores import StoreRepository

    db = AsyncMock()

    call_count = {"n": 0}

    async def execute(query, params=None):
        call_count["n"] += 1
        qtext = str(query)
        if "information_schema.columns" in qtext:
            return _FakeColumnCheckResult(exists=False)
        if "alert_threshold" in qtext and "FROM stores" in qtext:
            return _FakeMappingResult({
                "alert_threshold": 75.0,
                "alert_cooldown": 30,
                "telegram_chat_id": "@mychat",
            })
        return MagicMock()

    db.execute = execute

    repo = StoreRepository(db)
    settings = await repo.get_settings(1)

    assert settings.alert_threshold == 75.0
    assert settings.alert_cooldown_seconds == 30
    assert settings.notification_channels.telegram.chat_ids == ["@mychat"]


@pytest.mark.asyncio
async def test_get_settings_reads_jsonb_when_present():
    from shoplift_detector.app.db.repository.stores import StoreRepository

    async def execute(query, params=None):
        qtext = str(query)
        if "information_schema.columns" in qtext:
            return _FakeColumnCheckResult(exists=True)
        if "settings" in qtext and "FROM stores" in qtext:
            return _FakeMappingResult({
                "settings": {
                    "alert_threshold": 99.0,
                    "alert_cooldown_seconds": 120,
                    "night_mode_enabled": False,
                    "night_luminance_threshold": 50.0,
                    "dynamic_fps_enabled": True,
                    "fps_idle": 3,
                    "fps_active": 15,
                    "fps_suspicious": 30,
                    "clip_retention_normal_h": 48,
                    "clip_retention_alert_d": 30,
                    "face_blur_enabled": True,
                    "rag_check_enabled": True,
                    "rag_fp_threshold": 0.8,
                    "vlm_verification_enabled": True,
                    "vlm_confidence_threshold": 0.5,
                    "timezone": "Asia/Ulaanbaatar",
                    "notification_channels": {
                        "telegram": {"chat_ids": []},
                        "sms": {"numbers": []},
                        "email": {"addresses": []},
                    },
                },
                "alert_threshold": 99.0,
                "alert_cooldown": 120,
                "telegram_chat_id": None,
            })
        return MagicMock()

    db = AsyncMock()
    db.execute = execute

    repo = StoreRepository(db)
    settings = await repo.get_settings(1)

    assert settings.alert_threshold == 99.0
    assert settings.alert_cooldown_seconds == 120
    assert settings.night_mode_enabled is False


@pytest.mark.asyncio
async def test_update_settings_merges_patch_and_dual_writes_legacy_columns():
    from shoplift_detector.app.db.repository.stores import StoreRepository

    state = {
        "current": {
            "settings": default_settings_payload(),
            "alert_threshold": 80.0,
            "alert_cooldown": 60,
            "telegram_chat_id": None,
        },
        "last_update_params": None,
    }

    async def execute(query, params=None):
        qtext = str(query)
        if "information_schema.columns" in qtext:
            return _FakeColumnCheckResult(exists=True)
        if "UPDATE stores" in qtext:
            state["last_update_params"] = params
            return MagicMock()
        if "FROM stores" in qtext and "settings" in qtext:
            return _FakeMappingResult(state["current"])
        return MagicMock()

    db = AsyncMock()
    db.execute = execute

    repo = StoreRepository(db)
    patch = StoreSettingsPatch(alert_threshold=55.0, fps_suspicious=45)
    result = await repo.update_settings(1, patch)

    assert result.alert_threshold == 55.0
    assert result.fps_suspicious == 45
    assert result.alert_cooldown_seconds == 60  # preserved
    assert state["last_update_params"]["alert_threshold"] == 55.0
    assert state["last_update_params"]["alert_cooldown"] == 60
    db.commit.assert_awaited()

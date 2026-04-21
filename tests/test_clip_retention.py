import os
from datetime import UTC, datetime, timedelta

import pytest

from shoplift_detector.app.services.clip_retention import ClipRetentionCleaner, RetentionPolicy


class _MappingResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, query):
        return _MappingResult(self.rows)


def _touch(path, modified_at: datetime):
    path.write_bytes(b"media")
    ts = modified_at.timestamp()
    os.utime(path, (ts, ts))


@pytest.mark.asyncio
async def test_clip_retention_policy_deletes_only_expired_unprotected_media(tmp_path):
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    old_normal = tmp_path / "old-normal.mp4"
    fresh_normal = tmp_path / "fresh-normal.mp4"
    recent_alert = tmp_path / "recent-alert.mp4"
    expired_alert = tmp_path / "expired-alert.mp4"
    labeled_alert = tmp_path / "labeled-alert.mp4"

    for path in [old_normal, recent_alert, expired_alert, labeled_alert]:
        _touch(path, now - timedelta(hours=49))
    _touch(fresh_normal, now - timedelta(hours=1))

    rows = [
        {
            "image_path": None,
            "video_path": str(recent_alert),
            "event_time": now - timedelta(days=29),
            "is_labeled": False,
        },
        {
            "image_path": None,
            "video_path": str(expired_alert),
            "event_time": now - timedelta(days=31),
            "is_labeled": False,
        },
        {
            "image_path": None,
            "video_path": str(labeled_alert),
            "event_time": now - timedelta(days=365),
            "is_labeled": True,
        },
        {
            "image_path": "https://cdn.example.com/remote.mp4",
            "video_path": None,
            "event_time": now - timedelta(days=1),
            "is_labeled": True,
        },
    ]

    cleaner = ClipRetentionCleaner(
        media_dirs=[tmp_path],
        policy=RetentionPolicy(normal_hours=48, alert_days=30),
    )
    result = await cleaner.cleanup(_FakeDB(rows), now=now)

    assert not old_normal.exists()
    assert fresh_normal.exists()
    assert recent_alert.exists()
    assert not expired_alert.exists()
    assert labeled_alert.exists()
    assert result.scanned == 5
    assert result.deleted == 2
    assert result.kept_fresh_normal == 1
    assert result.kept_alert == 1
    assert result.kept_labeled == 1


def test_clip_retention_resolves_static_paths_by_basename(tmp_path):
    media = tmp_path / "alert_1.mp4"
    media.write_bytes(b"media")

    cleaner = ClipRetentionCleaner(media_dirs=[tmp_path])

    assert cleaner._resolve_media_path("/static/alert_1.mp4") == media.resolve()
    assert cleaner._resolve_media_path("https://example.com/alert_1.mp4") is None

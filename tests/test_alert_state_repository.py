from datetime import UTC, datetime, timedelta

import pytest

from shoplift_detector.app.db.repository.alert_state import (
    AlertStateRepository,
    normalize_camera_id,
)


class _MappingResult:
    def __init__(self, mapping=None):
        self._mapping = mapping

    def mappings(self):
        return self

    def fetchone(self):
        return self._mapping


class _RepoDB:
    def __init__(self):
        self.calls = []
        self.commits = 0

    async def execute(self, query, params):
        self.calls.append((str(query), params.copy()))
        return _MappingResult({"id": len(self.calls), **params})

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_alert_state_repository_writes_active_cooldown_and_resolved_states():
    db = _RepoDB()
    repo = AlertStateRepository(db)
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    cooldown_until = now + timedelta(seconds=60)

    await repo.mark_active(
        camera_id=7,
        person_track_id=42,
        now=now,
        cooldown_until=cooldown_until,
    )
    await repo.mark_cooldown(
        camera_id=7,
        person_track_id=42,
        alert_id=99,
        last_alert_at=now,
        cooldown_until=cooldown_until,
    )
    await repo.mark_resolved(
        camera_id=7,
        person_track_id=42,
        resolved_at=now + timedelta(seconds=61),
    )

    states = [params["state"] for _, params in db.calls]
    assert states == ["active", "cooldown", "resolved"]
    assert db.calls[1][1]["last_alert_id"] == 99
    assert db.calls[1][1]["cooldown_until"] == cooldown_until
    assert db.commits == 3


def test_normalize_camera_id_uses_zero_for_missing_camera():
    assert normalize_camera_id(None) == 0
    assert normalize_camera_id(7) == 7

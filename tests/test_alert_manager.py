from datetime import UTC, datetime, timedelta

import pytest

from shoplift_detector.app.services.alert_manager import AlertManager, AlertState


class _FakeResult:
    def __init__(self, row=None, mapping=None):
        self._row = row
        self._mapping = mapping

    def fetchone(self):
        return self._row

    def mappings(self):
        return _FakeResult(mapping=self._mapping)

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return self._row is not None or self._mapping is not None


class _FakeMappingResult:
    def __init__(self, mapping=None):
        self._mapping = mapping

    def mappings(self):
        return self

    def fetchone(self):
        return self._mapping


class _FakeDB:
    def __init__(self, event_time=None, state_row=None):
        self.event_time = event_time
        self.state_row = state_row
        self.calls = []
        self.commits = 0

    async def execute(self, query, params):
        query_text = str(query)
        self.calls.append((query_text, params))
        if "FROM alert_state" in query_text:
            return _FakeMappingResult(self.state_row)
        if "INSERT INTO alert_state" in query_text:
            return _FakeMappingResult(params)
        if self.event_time is None:
            return _FakeResult()
        return _FakeResult((self.event_time,))

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_alert_manager_suppresses_second_alert_from_memory():
    manager = AlertManager()
    db = _FakeDB()
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    first = await manager.should_send_alert(
        db,
        camera_id=7,
        person_track_id=42,
        cooldown_seconds=60,
        now=now,
    )
    second = await manager.should_send_alert(
        db,
        camera_id=7,
        person_track_id=42,
        cooldown_seconds=60,
        now=now + timedelta(seconds=10),
    )

    assert first.should_alert is True
    assert first.state == AlertState.ACTIVE
    assert second.should_alert is False
    assert second.state == AlertState.ACTIVE
    assert second.reason == "memory_active"


@pytest.mark.asyncio
async def test_alert_manager_restores_60_second_cooldown_from_alert_state():
    manager = AlertManager()
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    db = _FakeDB(state_row={
        "state": "cooldown",
        "last_alert_at": now - timedelta(seconds=30),
        "cooldown_until": now + timedelta(seconds=30),
    })

    decision = await manager.should_send_alert(
        db,
        camera_id=7,
        person_track_id=42,
        cooldown_seconds=60,
        now=now,
    )

    assert decision.should_alert is False
    assert decision.state == AlertState.COOLDOWN
    assert decision.reason == "state_table_cooldown"
    assert decision.cooldown_until == now + timedelta(seconds=30)


@pytest.mark.asyncio
async def test_alert_manager_restores_cooldown_from_persisted_alert():
    manager = AlertManager()
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    db = _FakeDB(event_time=now - timedelta(seconds=30))

    decision = await manager.should_send_alert(
        db,
        camera_id=7,
        person_track_id=42,
        cooldown_seconds=60,
        now=now,
    )

    assert decision.should_alert is False
    assert decision.state == AlertState.COOLDOWN
    assert decision.reason == "persisted_cooldown"


@pytest.mark.asyncio
async def test_alert_manager_allows_alert_after_persisted_cooldown_expires():
    manager = AlertManager()
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    db = _FakeDB(event_time=now - timedelta(seconds=61))

    decision = await manager.should_send_alert(
        db,
        camera_id=7,
        person_track_id=42,
        cooldown_seconds=60,
        now=now,
    )

    assert decision.should_alert is True
    assert decision.state == AlertState.ACTIVE


@pytest.mark.asyncio
async def test_alert_manager_scopes_lookup_by_camera_and_person_track():
    manager = AlertManager()
    db = _FakeDB()

    await manager.should_send_alert(
        db,
        camera_id=7,
        person_track_id=42,
        cooldown_seconds=60,
        now=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
    )

    query, params = next(
        (query, params)
        for query, params in db.calls
        if "FROM alerts" in query
    )
    assert "person_id = :person_track_id" in query
    assert "camera_id = :camera_id" in query
    assert params == {"person_track_id": 42, "camera_id": 7}

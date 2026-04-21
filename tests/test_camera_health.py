from datetime import UTC, datetime, timedelta

import pytest

from shoplift_detector.app.db.repository.camera_health import CameraHealthRepository
from shoplift_detector.app.services import camera_manager as camera_manager_module
from shoplift_detector.app.services.camera_manager import CameraManager, CameraState


class _MappingResult:
    def __init__(self, mapping=None, rows=None, rowcount=1):
        self._mapping = mapping
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._mapping

    def fetchall(self):
        return self._rows


class _RepoDB:
    def __init__(self, rows=None):
        self.calls = []
        self.commits = 0
        self.rows = rows or []

    async def execute(self, query, params):
        self.calls.append((str(query), params.copy()))
        if "SELECT" in str(query):
            return _MappingResult(rows=self.rows)
        return _MappingResult(mapping=params)

    async def commit(self):
        self.commits += 1


def _camera_state() -> CameraState:
    return CameraState(
        camera_id=12,
        store_id=3,
        name="Entrance",
        url="rtsp://example",
        camera_type="rtsp",
        is_ai_enabled=True,
    )


@pytest.mark.asyncio
async def test_camera_health_repository_upserts_online_and_offline_heartbeats():
    db = _RepoDB()
    repo = CameraHealthRepository(db)
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    await repo.upsert_heartbeat(
        camera_id=12,
        store_id=3,
        status="online",
        is_connected=True,
        fps=24.5,
        last_frame_at=now,
        now=now,
    )
    await repo.upsert_heartbeat(
        camera_id=12,
        store_id=3,
        status="offline",
        is_connected=False,
        fps=0,
        last_frame_at=now,
        last_error="frame_read_failed",
        now=now + timedelta(seconds=31),
    )

    assert db.calls[0][1]["status"] == "online"
    assert db.calls[0][1]["offline_since"] is None
    assert db.calls[1][1]["status"] == "offline"
    assert db.calls[1][1]["offline_since"] == now + timedelta(seconds=31)
    assert db.calls[1][1]["last_error"] == "frame_read_failed"
    assert db.commits == 2


@pytest.mark.asyncio
async def test_camera_health_repository_selects_offline_notification_candidates():
    row = {
        "camera_id": 12,
        "store_id": 3,
        "status": "offline",
        "offline_since": datetime(2026, 4, 20, 9, 55, tzinfo=UTC),
        "last_notification_at": None,
        "last_error": "frame_read_failed",
    }
    db = _RepoDB(rows=[row])
    repo = CameraHealthRepository(db)
    now = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    rows = await repo.get_offline_for_notification(
        offline_for_seconds=300,
        notification_interval_seconds=300,
        now=now,
    )

    assert rows == [row]
    params = db.calls[0][1]
    assert params["offline_before"] == now - timedelta(seconds=300)
    assert params["notify_before"] == now - timedelta(seconds=300)


def test_camera_manager_health_status_changes_from_degraded_to_offline(monkeypatch):
    manager = CameraManager()
    state = _camera_state()
    manager._mark_offline(state, "frame_read_failed")

    monkeypatch.setattr(camera_manager_module.settings, "CAMERA_HEALTH_OFFLINE_AFTER_SECONDS", 30)
    assert manager._get_health_status(state) == "degraded"

    state.offline_since_monotonic -= 31
    assert manager._get_health_status(state) == "offline"


def test_camera_manager_reconnect_backoff_is_exponential_and_capped(monkeypatch):
    manager = CameraManager()
    monkeypatch.setattr(camera_manager_module.settings, "RTSP_RECONNECT_BASE", 1.0)
    monkeypatch.setattr(camera_manager_module.settings, "RTSP_RECONNECT_MAX", 60.0)

    max_backoff = manager._reconnect_max_backoff()
    values = [manager._reconnect_base_backoff()]
    for _ in range(8):
        values.append(manager._next_reconnect_backoff(values[-1], max_backoff))

    assert values == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]


def test_camera_manager_reconnect_backoff_never_exceeds_60_seconds(monkeypatch):
    manager = CameraManager()
    monkeypatch.setattr(camera_manager_module.settings, "RTSP_RECONNECT_BASE", 5.0)
    monkeypatch.setattr(camera_manager_module.settings, "RTSP_RECONNECT_MAX", 120.0)

    max_backoff = manager._reconnect_max_backoff()

    assert max_backoff == 60.0
    assert manager._next_reconnect_backoff(45.0, max_backoff) == 60.0


def test_camera_manager_status_includes_health_status(monkeypatch):
    manager = CameraManager()
    state = _camera_state()
    manager._mark_offline(state, "frame_read_failed")
    state.offline_since_monotonic -= 31
    manager._cameras[state.camera_id] = state

    monkeypatch.setattr(camera_manager_module.settings, "CAMERA_HEALTH_OFFLINE_AFTER_SECONDS", 30)
    [status] = manager.get_all_status()

    assert status["camera_id"] == 12
    assert status["health_status"] == "offline"
    assert status["last_error"] == "frame_read_failed"

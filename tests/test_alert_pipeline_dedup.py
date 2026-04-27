"""Integration-style tests for the alert dispatch pipeline.

Verifies that ai_service._dispatch_alert routes every alert through the
AlertManager dedup gate: Telegram and alert_queue must not fire when the
gate returns should_alert=False, and record_alert_committed must fire
when the gate approves.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoplift_detector.app.services.alert_manager import AlertDecision, AlertState


class _FakeSession:
    """Minimal async-context-manager stand-in for AsyncSessionLocal()."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_detector():
    """Instantiate ShopliftDetector without loading YOLO weights."""
    from shoplift_detector.app.services import ai_service

    detector = ai_service.ShopliftDetector.__new__(ai_service.ShopliftDetector)
    detector.executor = MagicMock()
    return detector


@pytest.mark.asyncio
async def test_dispatch_alert_suppresses_on_cooldown():
    detector = _make_detector()
    now = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)

    manager = MagicMock()
    manager.should_send_alert = AsyncMock(return_value=AlertDecision(
        should_alert=False,
        state=AlertState.COOLDOWN,
        reason="memory_cooldown",
        cooldown_until=now + timedelta(seconds=30),
    ))
    manager.record_alert_committed = AsyncMock()

    dispatch_escalation = AsyncMock()
    queue = MagicMock()

    with patch("app.db.session.AsyncSessionLocal", _FakeSession), \
         patch("app.services.alert_manager.alert_manager", manager), \
         patch("app.services.storage.get_storage") as storage, \
         patch(
             "app.services.escalation_dispatcher.dispatch_alert",
             dispatch_escalation,
         ), \
         patch("app.core.state.alert_queue", queue):
        await detector._dispatch_alert(
            yolo_id=42,
            frame_to_save=MagicMock(),
            name="Unknown",
            reason="test",
            bbox=[0, 0, 10, 10],
            camera_id=7,
            store_id=3,
            score=95.0,
            cooldown_seconds=60,
        )

    manager.should_send_alert.assert_awaited_once()
    manager.record_alert_committed.assert_not_awaited()
    dispatch_escalation.assert_not_awaited()
    storage.assert_not_called()
    queue.put.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_alert_persists_and_notifies_when_approved():
    detector = _make_detector()
    now = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)

    manager = MagicMock()
    manager.should_send_alert = AsyncMock(return_value=AlertDecision(
        should_alert=True,
        state=AlertState.ACTIVE,
        reason="new_alert",
        cooldown_until=now + timedelta(seconds=60),
    ))
    manager.record_alert_committed = AsyncMock()

    dispatch_escalation = AsyncMock()
    queue = MagicMock()

    storage_instance = MagicMock()
    storage_instance.save_image.return_value = "https://cdn/alert.jpg"

    repo_instance = MagicMock()
    repo_instance.insert_alert = AsyncMock(return_value=1234)

    # T9 RAG/VLM pipeline — return a passing decision so the dispatch
    # path matches its pre-pipeline behavior. The pipeline itself is
    # tested separately in tests/test_rag_vlm_pipeline.py.
    from app.services.rag_vlm_pipeline import PipelineDecision
    pipeline_eval = AsyncMock(return_value=PipelineDecision(
        rag_decision="not_run", vlm_decision="not_run", suppressed=False,
    ))
    store_repo = MagicMock()
    store_repo.get_by_id = AsyncMock(return_value={"id": 3, "settings": None})

    with patch("app.db.session.AsyncSessionLocal", _FakeSession), \
         patch("app.services.alert_manager.alert_manager", manager), \
         patch("app.services.storage.get_storage", return_value=storage_instance), \
         patch("app.db.repository.alerts.AlertRepository", return_value=repo_instance), \
         patch("app.db.repository.stores.StoreRepository", return_value=store_repo), \
         patch("app.services.rag_vlm_pipeline.evaluate", pipeline_eval), \
         patch(
             "app.services.escalation_dispatcher.dispatch_alert",
             dispatch_escalation,
         ), \
         patch("app.core.state.alert_queue", queue):
        await detector._dispatch_alert(
            yolo_id=42,
            frame_to_save=MagicMock(),
            name="Unknown",
            reason="test",
            bbox=[0, 0, 10, 10],
            camera_id=7,
            store_id=3,
            score=95.0,
            cooldown_seconds=60,
        )

    manager.should_send_alert.assert_awaited_once()
    repo_instance.insert_alert.assert_awaited_once()
    manager.record_alert_committed.assert_awaited_once()
    dispatch_escalation.assert_awaited_once()
    # T5-09 — the dispatcher gets the alert_id produced by insert_alert.
    (_call_args, _) = dispatch_escalation.await_args
    # Called positionally with AlertContext.
    ctx = dispatch_escalation.await_args[0][0]
    assert ctx.alert_id == 1234
    queue.put.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_alert_aborts_without_recording_if_insert_returns_none():
    detector = _make_detector()
    now = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)

    manager = MagicMock()
    manager.should_send_alert = AsyncMock(return_value=AlertDecision(
        should_alert=True,
        state=AlertState.ACTIVE,
        reason="new_alert",
        cooldown_until=now + timedelta(seconds=60),
    ))
    manager.record_alert_committed = AsyncMock()

    telegram = AsyncMock()
    queue = MagicMock()

    storage_instance = MagicMock()
    storage_instance.save_image.return_value = "https://cdn/alert.jpg"

    repo_instance = MagicMock()
    repo_instance.insert_alert = AsyncMock(return_value=None)

    from app.services.rag_vlm_pipeline import PipelineDecision
    pipeline_eval = AsyncMock(return_value=PipelineDecision(
        rag_decision="not_run", vlm_decision="not_run", suppressed=False,
    ))
    store_repo = MagicMock()
    store_repo.get_by_id = AsyncMock(return_value={"id": 3, "settings": None})

    with patch("app.db.session.AsyncSessionLocal", _FakeSession), \
         patch("app.services.alert_manager.alert_manager", manager), \
         patch("app.services.storage.get_storage", return_value=storage_instance), \
         patch("app.db.repository.alerts.AlertRepository", return_value=repo_instance), \
         patch("app.db.repository.stores.StoreRepository", return_value=store_repo), \
         patch("app.services.rag_vlm_pipeline.evaluate", pipeline_eval), \
         patch.object(detector, "_send_telegram_alert", telegram), \
         patch("app.core.state.alert_queue", queue):
        await detector._dispatch_alert(
            yolo_id=42,
            frame_to_save=MagicMock(),
            name="Unknown",
            reason="test",
            bbox=[0, 0, 10, 10],
            camera_id=7,
            store_id=3,
            score=95.0,
            cooldown_seconds=60,
        )

    manager.record_alert_committed.assert_not_awaited()
    telegram.assert_not_awaited()
    queue.put.assert_not_called()

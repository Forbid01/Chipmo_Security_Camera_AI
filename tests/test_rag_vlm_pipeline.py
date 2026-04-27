"""Tests for the RAG + VLM orchestrator (`rag_vlm_pipeline.evaluate`).

Asserts the four failure / decision branches the alert dispatch path
relies on:

1. Both layers disabled in store settings → "not_run" / "not_run".
2. RAG suppression short-circuits and does not call the VLM (cost
   safety — the VLM is the expensive layer).
3. VLM verdict below confidence threshold → "suppressed_by_vlm".
4. RAG / VLM exceptions are caught and downgrade to "not_run" so the
   alert path keeps working when Qdrant or the GPU is down.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from shoplift_detector.app.schemas.store_settings import StoreSettings
from shoplift_detector.app.services import rag_vlm_pipeline


def _frame() -> np.ndarray:
    return np.zeros((64, 64, 3), dtype=np.uint8)


def _settings(**overrides) -> StoreSettings:
    base = StoreSettings()
    return base.model_copy(update=overrides)


@pytest.mark.asyncio
async def test_both_disabled_returns_not_run():
    cfg = _settings(rag_check_enabled=False, vlm_verification_enabled=False)
    decision = await rag_vlm_pipeline.evaluate(
        description="x", frame=_frame(), store_id=1, store_settings=cfg, db=AsyncMock()
    )
    assert decision.rag_decision == "not_run"
    assert decision.vlm_decision == "not_run"
    assert decision.suppressed is False


@pytest.mark.asyncio
async def test_rag_suppression_skips_vlm():
    """If RAG already decided this is a known FP, the VLM is too
    expensive to run — the test guards against future code adding a
    "validate anyway" branch."""
    cfg = _settings(rag_check_enabled=True, vlm_verification_enabled=True)
    rag_result = MagicMock(
        should_suppress=True,
        fp_score=0.95,
        top_docs=[],
        reason="matches known_fp 'doc-1'",
    )
    with patch(
        "app.services.rag_retriever.evaluate_alert",
        AsyncMock(return_value=rag_result),
    ), patch(
        "app.services.vlm_service.describe_alert",
        AsyncMock(side_effect=AssertionError("VLM must not be called")),
    ), patch.object(rag_vlm_pipeline.settings, "RAG_ENABLED", True), \
         patch.object(rag_vlm_pipeline.settings, "VLM_ENABLED", True):
        decision = await rag_vlm_pipeline.evaluate(
            description="x", frame=_frame(), store_id=1, store_settings=cfg, db=AsyncMock()
        )
    assert decision.rag_decision == "suppressed_by_rag"
    assert decision.vlm_decision == "not_run"
    assert decision.suppressed is True
    assert decision.suppressed_reason == "matches known_fp 'doc-1'"


@pytest.mark.asyncio
async def test_vlm_below_threshold_suppresses():
    cfg = _settings(
        rag_check_enabled=False,
        vlm_verification_enabled=True,
        vlm_confidence_threshold=0.6,
    )
    verdict = MagicMock(
        caption="Customer browsing the shelf normally",
        confidence=0.3,
        reasoning={"is_shoplifting": False},
        latency_ms=1200,
        model_name="Qwen/Qwen2.5-VL-7B-Instruct",
    )
    with patch(
        "app.services.vlm_service.describe_alert",
        AsyncMock(return_value=verdict),
    ), patch.object(rag_vlm_pipeline.settings, "VLM_ENABLED", True):
        decision = await rag_vlm_pipeline.evaluate(
            description="suspicious crouch", frame=_frame(), store_id=1, store_settings=cfg, db=AsyncMock()
        )
    assert decision.vlm_decision == "suppressed_by_vlm"
    assert decision.suppressed is True
    assert "0.30" in decision.suppressed_reason
    assert decision.vlm_verdict is verdict


@pytest.mark.asyncio
async def test_vlm_above_threshold_passes():
    cfg = _settings(
        rag_check_enabled=False,
        vlm_verification_enabled=True,
        vlm_confidence_threshold=0.5,
    )
    verdict = MagicMock(
        caption="Person concealing item under jacket",
        confidence=0.85,
        reasoning={"is_shoplifting": True},
        latency_ms=1100,
        model_name="Qwen/Qwen2.5-VL-7B-Instruct",
    )
    with patch(
        "app.services.vlm_service.describe_alert",
        AsyncMock(return_value=verdict),
    ), patch.object(rag_vlm_pipeline.settings, "VLM_ENABLED", True):
        decision = await rag_vlm_pipeline.evaluate(
            description="x", frame=_frame(), store_id=1, store_settings=cfg, db=AsyncMock()
        )
    assert decision.vlm_decision == "passed"
    assert decision.suppressed is False


@pytest.mark.asyncio
async def test_rag_exception_downgrades_to_not_run():
    """A flaky Qdrant must never block real alerts. The caught
    exception path should let the pipeline continue past RAG."""
    cfg = _settings(rag_check_enabled=True, vlm_verification_enabled=False)
    with patch(
        "app.services.rag_retriever.evaluate_alert",
        AsyncMock(side_effect=ConnectionError("qdrant down")),
    ), patch.object(rag_vlm_pipeline.settings, "RAG_ENABLED", True):
        decision = await rag_vlm_pipeline.evaluate(
            description="x", frame=_frame(), store_id=1, store_settings=cfg, db=AsyncMock()
        )
    assert decision.rag_decision == "not_run"
    assert decision.suppressed is False


@pytest.mark.asyncio
async def test_vlm_timeout_downgrades_to_not_run():
    """asyncio.TimeoutError specifically — the orchestrator must catch
    it (vs. letting it bubble up and crash the dispatch task)."""
    import asyncio

    cfg = _settings(
        rag_check_enabled=False,
        vlm_verification_enabled=True,
        vlm_confidence_threshold=0.5,
    )
    with patch(
        "app.services.vlm_service.describe_alert",
        AsyncMock(side_effect=asyncio.TimeoutError()),
    ), patch.object(rag_vlm_pipeline.settings, "VLM_ENABLED", True):
        decision = await rag_vlm_pipeline.evaluate(
            description="x", frame=_frame(), store_id=1, store_settings=cfg, db=AsyncMock()
        )
    assert decision.vlm_decision == "not_run"
    assert decision.suppressed is False


@pytest.mark.asyncio
async def test_no_store_id_skips_rag_entirely():
    """RAG corpus is store-scoped. Legacy alerts with store_id=None
    have nothing to retrieve — the pipeline must skip RAG cleanly
    rather than throwing on a missing tenant filter."""
    cfg = _settings(rag_check_enabled=True, vlm_verification_enabled=False)
    with patch(
        "app.services.rag_retriever.evaluate_alert",
        AsyncMock(side_effect=AssertionError("RAG must not be called")),
    ), patch.object(rag_vlm_pipeline.settings, "RAG_ENABLED", True):
        decision = await rag_vlm_pipeline.evaluate(
            description="x", frame=_frame(), store_id=None, store_settings=cfg, db=None
        )
    assert decision.rag_decision == "not_run"
    assert decision.suppressed is False

"""RAG + VLM verification orchestrator.

Wraps the two layers in a single async entry point that the alert
dispatch path calls right before it persists. The orchestrator:

1. Reads per-store toggles + thresholds from `StoreSettings`.
2. Asks the RAG retriever whether the alert matches a known false
   positive. If yes → suppress immediately, skip the VLM (cheaper).
3. Otherwise asks Qwen2.5-VL whether the frame really shows shoplifting.
   If `confidence < vlm_confidence_threshold` → suppress.
4. Returns a `PipelineDecision` whose fields map 1:1 to the alert
   columns (`rag_decision`, `vlm_decision`, `suppressed`,
   `suppressed_reason`).

Failure handling is conservative: any exception in either layer
downgrades the verdict to "not_run" and lets the alert pass through.
We'd rather over-alert than silently drop a real shoplifting incident
because Qdrant or the VLM hiccupped.

VLM annotations are persisted asynchronously via
`enqueue_vlm_annotation` so the dispatch path doesn't block on a 1-5s
GPU forward. The orchestrator's *decision* still uses the synchronous
verdict — the queued task only writes the cached row for the frontend.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.schemas.store_settings import StoreSettings

if TYPE_CHECKING:
    import numpy as np
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class PipelineDecision:
    """Verdict for the alert dispatch path.

    `rag_decision` / `vlm_decision` / `suppressed` / `suppressed_reason`
    are written verbatim to the matching `alerts` columns. `vlm_verdict`
    is the raw VLM result (or None) — kept on the decision so the
    background annotation task doesn't have to re-run inference.
    """

    rag_decision: str = "not_run"
    vlm_decision: str = "not_run"
    suppressed: bool = False
    suppressed_reason: str | None = None
    vlm_verdict: Any | None = None
    rag_top_docs: list[Any] = field(default_factory=list)


async def evaluate(
    *,
    description: str,
    frame: "np.ndarray",
    store_id: int | None,
    store_settings: StoreSettings | None,
    db: "AsyncSession | None" = None,
) -> PipelineDecision:
    """Run RAG → VLM and return a single verdict.

    `store_settings` is the resolved StoreSettings for the alert's store.
    A None store_id (legacy alerts without a store) skips RAG entirely
    because the corpus is store-scoped — there's nothing to retrieve.

    `db` is the AsyncSession the dispatch path is already holding open.
    pgvector retrieval runs over this session so the search inherits
    the same tenancy/RLS context that committed the alert.
    """
    decision = PipelineDecision()
    cfg = store_settings or StoreSettings()

    # --- RAG layer ---------------------------------------------------
    rag_enabled = (
        settings.RAG_ENABLED
        and cfg.rag_check_enabled
        and store_id is not None
        and bool(description)
        and db is not None
    )
    if rag_enabled:
        try:
            from app.services import rag_retriever

            rag_result = await rag_retriever.evaluate_alert(
                db,
                store_id=store_id,
                alert_description=description,
                fp_threshold=cfg.rag_fp_threshold,
            )
            decision.rag_top_docs = rag_result.top_docs
            if rag_result.should_suppress:
                decision.rag_decision = "suppressed_by_rag"
                decision.suppressed = True
                decision.suppressed_reason = rag_result.reason
                # Skip VLM — RAG already decided this is a known FP.
                return decision
            decision.rag_decision = "passed"
        except Exception:
            logger.exception("RAG evaluation failed; passing through")
            decision.rag_decision = "not_run"

    # --- VLM layer ---------------------------------------------------
    vlm_enabled = (
        settings.VLM_ENABLED
        and cfg.vlm_verification_enabled
        and frame is not None
    )
    if vlm_enabled:
        try:
            from app.services import vlm_service

            verdict = await vlm_service.describe_alert(
                frame=frame, description=description
            )
            decision.vlm_verdict = verdict
            if verdict.confidence < cfg.vlm_confidence_threshold:
                decision.vlm_decision = "suppressed_by_vlm"
                decision.suppressed = True
                decision.suppressed_reason = (
                    f"VLM confidence {verdict.confidence:.2f} "
                    f"< threshold {cfg.vlm_confidence_threshold:.2f}: "
                    f"{verdict.caption[:160]}"
                )
            else:
                decision.vlm_decision = "passed"
        except asyncio.TimeoutError:
            logger.warning("VLM timeout for store_id=%s; passing through", store_id)
            decision.vlm_decision = "not_run"
        except Exception:
            logger.exception("VLM evaluation failed; passing through")
            decision.vlm_decision = "not_run"

    return decision


async def persist_vlm_annotation(
    *,
    db: "AsyncSession",
    alert_id: int,
    verdict: Any,
) -> None:
    """Write a VlmAnnotation row for an alert. Idempotent on alert_id."""
    from app.db.models.vlm_annotation import VlmAnnotation
    from sqlalchemy import select

    existing = await db.execute(
        select(VlmAnnotation).where(VlmAnnotation.alert_id == alert_id)
    )
    if existing.scalar_one_or_none():
        return

    db.add(
        VlmAnnotation(
            alert_id=alert_id,
            model_name=verdict.model_name,
            caption=verdict.caption,
            confidence=verdict.confidence,
            reasoning=verdict.reasoning,
            latency_ms=verdict.latency_ms,
        )
    )
    await db.commit()


def enqueue_vlm_annotation(alert_id: int, verdict: Any) -> None:
    """Fire-and-forget the VLM annotation persist.

    Called from the dispatch path after the alert is committed. We open
    a fresh session inside the task so the caller's session can close
    immediately and the task survives the request lifecycle.
    """
    if verdict is None:
        return

    async def _run() -> None:
        from app.core.tenancy_context import system_bypass
        from app.db.session import AsyncSessionLocal

        try:
            with system_bypass():
                async with AsyncSessionLocal() as db:
                    await persist_vlm_annotation(
                        db=db, alert_id=alert_id, verdict=verdict
                    )
        except Exception:
            logger.exception(
                "Failed to persist VLM annotation for alert_id=%s", alert_id
            )

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        # No running loop — fall back to a fresh one (should not happen
        # from the dispatch path, but cheap to be safe).
        asyncio.run(_run())

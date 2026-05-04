"""Cross-camera Re-Identification service.

Extracts 576-dim appearance embeddings from person crops using
MobileNetV3-Small (torchvision, already in requirements). Embeddings are
L2-normalised and stored in the `person_embeddings` pgvector table.
Cosine similarity search finds the same person across cameras within the
same store.

Two-phase integration with the alert pipeline
─────────────────────────────────────────────
Phase 1 (BEFORE alert insert):
    `reid_service.lookup_person_id(frame, bbox, store_id, camera_id, db)`
    → extracts embedding
    → searches person_embeddings for a match within the 5s HANDOFF window
    → if found: returns the existing person_id so the new alert shares it
    → if not found: returns None → caller generates a new P-{store}-…-{seq}

Phase 2 (AFTER alert insert):
    `reid_service.store_embedding_for_alert(db, embedding, alert_id, ...)`
    → persists the embedding row with the new alert_id
    `reid_service.handoff_tracker.record(store_id, person_id)`
    → registers the person in the 5s in-memory window

Architecture notes
──────────────────
- Model is lazy-loaded on first alert; never blocks the inference loop.
- Embedding extraction is synchronous (CPU, ~5ms per crop); called from
  the AI thread.
- DB writes and queries are async; run on the main event loop via
  `camera_manager._submit_async` (same pattern as health reports).
- Disabled gracefully when torch/torchvision are not installed.
- HandoffTracker requires no Redis — safe for Railway single-process.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

REID_EMBEDDING_DIM   = 576
REID_MATCH_THRESHOLD = 0.75   # cosine similarity ≥ this → same person
REID_WINDOW_MINUTES  = 30     # long-range search window
REID_HANDOFF_SECONDS = 5.0    # short window for cross-camera handoff


# ---------------------------------------------------------------------------
# 5-second handoff tracker (in-memory, no Redis)
# ---------------------------------------------------------------------------

class HandoffTracker:
    """Track recently-seen person IDs to detect cross-camera handoffs.

    When a person triggers an alert on Camera A, we record their person_id
    with a timestamp. If the same person_id appears on Camera B within
    REID_HANDOFF_SECONDS, the new alert reuses the existing person_id
    (same incident, different camera view) rather than minting a new one.

    Keeps the dict bounded by evicting entries older than 4× the window
    on every write — cheap enough to skip a background cleaner thread.
    """

    _EVICT_MULTIPLIER = 4

    def __init__(self, window_s: float = REID_HANDOFF_SECONDS) -> None:
        self._window_s = window_s
        self._seen: dict[tuple[int, str], float] = {}   # (store_id, person_id) → monotonic ts
        self._lock = threading.Lock()

    def record(self, store_id: int, person_id: str) -> None:
        """Mark person_id as recently seen in store_id."""
        key = (store_id, person_id)
        now = time.monotonic()
        with self._lock:
            self._seen[key] = now
            self._evict(now)

    def is_within_window(self, store_id: int, person_id: str) -> bool:
        """Return True if person_id was seen in store_id within the window."""
        key = (store_id, person_id)
        with self._lock:
            ts = self._seen.get(key)
        return ts is not None and (time.monotonic() - ts) <= self._window_s

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_s * self._EVICT_MULTIPLIER
        stale = [k for k, ts in self._seen.items() if ts < cutoff]
        for k in stale:
            del self._seen[k]


# ---------------------------------------------------------------------------
# Re-ID service
# ---------------------------------------------------------------------------

class ReIDService:
    """Singleton Re-ID service — lazy model load, thread-safe."""

    def __init__(self) -> None:
        self._model = None
        self._transform = None
        self._lock = threading.Lock()
        self._enabled: bool | None = None   # None = not yet tried
        self._device: str = "cpu"
        self.handoff_tracker = HandoffTracker()

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load MobileNetV3-Small feature extractor (no classifier head)."""
        try:
            import torch
            import torch.nn as nn
            import torchvision.models as tvm
            import torchvision.transforms as T

            weights = tvm.MobileNet_V3_Small_Weights.IMAGENET1K_V1
            model = tvm.mobilenet_v3_small(weights=weights)
            # Drop the classifier → forward() returns 576-dim feature maps.
            model.classifier = nn.Identity()
            model.eval()

            self._device = (
                "cuda"
                if torch.cuda.is_available()
                else "mps"
                if getattr(torch.backends, "mps", None)
                and torch.backends.mps.is_available()
                else "cpu"
            )
            model = model.to(self._device)

            self._transform = T.Compose([
                T.Resize((224, 224)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            self._model = model
            self._enabled = True
            logger.info("reid_model_loaded device=%s", self._device)
        except Exception as exc:
            logger.warning("reid_model_load_failed: %s — Re-ID disabled", exc)
            self._enabled = False

    def _get_model(self):
        if self._enabled is None:
            with self._lock:
                if self._enabled is None:
                    self._load_model()
        return self._model if self._enabled else None

    # ------------------------------------------------------------------
    # Embedding extraction (synchronous, called from inference thread)
    # ------------------------------------------------------------------

    def extract_embedding(
        self,
        frame: np.ndarray,
        bbox: list[float],
    ) -> np.ndarray | None:
        """Extract L2-normalised 576-dim embedding from a person crop.

        Args:
            frame: Full display frame in BGR (OpenCV).
            bbox:  [x1, y1, x2, y2] in pixel coords of the full frame.

        Returns:
            float32 ndarray shape (576,) or None on failure.
        """
        model = self._get_model()
        if model is None:
            return None

        try:
            import cv2
            import torch
            from PIL import Image

            x1, y1, x2, y2 = (int(v) for v in bbox)
            x1, x2 = max(0, x1), min(frame.shape[1], x2)
            y1, y2 = max(0, y1), min(frame.shape[0], y2)
            if x2 - x1 < 8 or y2 - y1 < 8:
                return None

            crop = frame[y1:y2, x1:x2]
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(crop_rgb)

            tensor = self._transform(img).unsqueeze(0).to(self._device)
            with torch.no_grad():
                feat = model(tensor).squeeze(0)
                feat = feat / (feat.norm() + 1e-8)  # L2 normalise

            return feat.cpu().float().numpy()
        except Exception as exc:
            logger.debug("reid_embedding_failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Phase 1: lookup person_id before alert insert
    # ------------------------------------------------------------------

    async def lookup_person_id(
        self,
        *,
        frame: np.ndarray,
        bbox: list[float],
        store_id: int,
        camera_id: int,
        db,
    ) -> tuple[np.ndarray | None, str | None]:
        """Extract embedding and search for a cross-camera handoff match.

        Returns:
            (embedding, matched_person_id)

            embedding          — float32 (576,) or None if extraction failed
            matched_person_id  — person_id string from a matching alert within
                                 REID_HANDOFF_SECONDS, or None if no match
        """
        embedding = self.extract_embedding(frame, bbox)
        if embedding is None:
            return None, None

        matches = await self._find_handoff_matches(
            db,
            store_id=store_id,
            embedding=embedding,
            exclude_camera_id=camera_id,
        )

        if not matches:
            return embedding, None

        # Best match (highest similarity) within the handoff window.
        best = matches[0]
        person_id: str | None = best.get("matched_person_id")

        # Extra guard: confirm the handoff tracker hasn't already expired it.
        if person_id and self.handoff_tracker.is_within_window(store_id, person_id):
            logger.info(
                "reid_handoff store=%s camera=%s→%s person_id=%s sim=%.3f",
                store_id,
                best.get("camera_id"),
                camera_id,
                person_id,
                best.get("similarity", 0),
            )
            return embedding, person_id

        # Match found in DB but tracker window expired — treat as new person.
        return embedding, None

    # ------------------------------------------------------------------
    # Phase 2: store embedding after alert insert
    # ------------------------------------------------------------------

    async def store_embedding_for_alert(
        self,
        db,
        *,
        embedding: np.ndarray,
        store_id: int,
        camera_id: int,
        track_id: int,
        alert_id: int,
        bbox: list[float],
        captured_at: datetime | None = None,
    ) -> int | None:
        """Persist an embedding row linked to an alert. Returns row id."""
        from sqlalchemy import text

        now = datetime.now(UTC)
        ts = captured_at or now

        try:
            result = await db.execute(
                text(
                    """
                    INSERT INTO person_embeddings
                        (store_id, camera_id, alert_id, track_id, embedding,
                         bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                         captured_at, created_at)
                    VALUES
                        (:store_id, :camera_id, :alert_id, :track_id, :embedding,
                         :x1, :y1, :x2, :y2,
                         :captured_at, :created_at)
                    RETURNING id
                    """
                ),
                {
                    "store_id": store_id,
                    "camera_id": camera_id,
                    "alert_id": alert_id,
                    "track_id": int(track_id),
                    "embedding": embedding.tolist(),
                    "x1": float(bbox[0]),
                    "y1": float(bbox[1]),
                    "x2": float(bbox[2]),
                    "y2": float(bbox[3]),
                    "captured_at": ts,
                    "created_at": now,
                },
            )
            await db.commit()
            row = result.fetchone()
            return row[0] if row else None
        except Exception as exc:
            logger.warning("reid_store_embedding_failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal: handoff-window DB query (5s, joins alert for person_id)
    # ------------------------------------------------------------------

    async def _find_handoff_matches(
        self,
        db,
        *,
        store_id: int,
        embedding: np.ndarray,
        exclude_camera_id: int,
        threshold: float = REID_MATCH_THRESHOLD,
        limit: int = 3,
    ) -> list[dict]:
        """Return top matches from other cameras captured within 5 seconds.

        Joins person_embeddings → alerts to retrieve the matched person_id
        so the caller can reuse it for the new alert (cross-camera identity).
        """
        from sqlalchemy import text

        since = datetime.now(UTC) - timedelta(seconds=REID_HANDOFF_SECONDS)

        try:
            result = await db.execute(
                text(
                    """
                    SELECT
                        pe.id,
                        pe.camera_id,
                        pe.alert_id,
                        pe.track_id,
                        a.person_id  AS matched_person_id,
                        1 - (pe.embedding <=> :embedding::vector) AS similarity,
                        pe.bbox_x1, pe.bbox_y1, pe.bbox_x2, pe.bbox_y2,
                        pe.captured_at
                    FROM person_embeddings pe
                    LEFT JOIN alerts a ON a.id = pe.alert_id
                    WHERE pe.store_id    = :store_id
                      AND pe.camera_id != :exclude_camera_id
                      AND pe.captured_at >= :since
                      AND 1 - (pe.embedding <=> :embedding::vector) >= :threshold
                    ORDER BY similarity DESC
                    LIMIT :limit
                    """
                ),
                {
                    "embedding": embedding.tolist(),
                    "store_id": store_id,
                    "exclude_camera_id": exclude_camera_id,
                    "since": since,
                    "threshold": threshold,
                    "limit": limit,
                },
            )
            rows = result.mappings().fetchall()
            return [
                {
                    "embedding_id": r["id"],
                    "camera_id": r["camera_id"],
                    "alert_id": r["alert_id"],
                    "track_id": r["track_id"],
                    "matched_person_id": r["matched_person_id"],
                    "similarity": round(float(r["similarity"]), 4),
                    "bbox": [r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"]],
                    "captured_at": r["captured_at"].isoformat() if r["captured_at"] else None,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("reid_handoff_query_failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Long-range cross-camera match query (for the /reid/matches endpoint)
    # ------------------------------------------------------------------

    async def find_cross_camera_matches(
        self,
        db,
        *,
        store_id: int,
        embedding: np.ndarray,
        exclude_camera_id: int,
        threshold: float = REID_MATCH_THRESHOLD,
        since_minutes: int = REID_WINDOW_MINUTES,
        limit: int = 5,
    ) -> list[dict]:
        """Return top-k matches from other cameras in the 30-min window.

        Used by GET /api/v1/cameras/reid/matches/{alert_id}.
        Returns dicts with camera_id, alert_id, track_id, similarity,
        bbox, captured_at — sorted by descending similarity.
        """
        from sqlalchemy import text

        since = datetime.now(UTC) - timedelta(minutes=since_minutes)

        try:
            result = await db.execute(
                text(
                    """
                    SELECT
                        pe.id,
                        pe.camera_id,
                        pe.alert_id,
                        pe.track_id,
                        1 - (pe.embedding <=> :embedding::vector) AS similarity,
                        pe.bbox_x1, pe.bbox_y1, pe.bbox_x2, pe.bbox_y2,
                        pe.captured_at
                    FROM person_embeddings pe
                    WHERE pe.store_id    = :store_id
                      AND pe.camera_id != :exclude_camera_id
                      AND pe.captured_at >= :since
                      AND 1 - (pe.embedding <=> :embedding::vector) >= :threshold
                    ORDER BY similarity DESC
                    LIMIT :limit
                    """
                ),
                {
                    "embedding": embedding.tolist(),
                    "store_id": store_id,
                    "exclude_camera_id": exclude_camera_id,
                    "since": since,
                    "threshold": threshold,
                    "limit": limit,
                },
            )
            rows = result.mappings().fetchall()
            return [
                {
                    "embedding_id": r["id"],
                    "camera_id": r["camera_id"],
                    "alert_id": r["alert_id"],
                    "track_id": r["track_id"],
                    "similarity": round(float(r["similarity"]), 4),
                    "bbox": [r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"]],
                    "captured_at": r["captured_at"].isoformat() if r["captured_at"] else None,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("reid_find_matches_failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Legacy entry point (kept for backward compatibility with existing
    # callers; new code should use lookup_person_id + store_embedding_for_alert)
    # ------------------------------------------------------------------

    async def process_alert_embedding(
        self,
        *,
        frame: np.ndarray,
        bbox: list[float],
        store_id: int,
        camera_id: int,
        track_id: int,
        alert_id: int,
    ) -> list[dict]:
        """Extract embedding, store it, and search for 30-min matches.

        Kept for backward-compat. New pipeline uses the two-phase API.
        """
        from app.core.tenancy_context import system_bypass
        from app.db.session import AsyncSessionLocal

        embedding = self.extract_embedding(frame, bbox)
        if embedding is None:
            return []

        with system_bypass():
            async with AsyncSessionLocal() as db:
                await self.store_embedding_for_alert(
                    db,
                    embedding=embedding,
                    store_id=store_id,
                    camera_id=camera_id,
                    track_id=track_id,
                    bbox=bbox,
                    alert_id=alert_id,
                    captured_at=datetime.now(UTC),
                )
                matches = await self.find_cross_camera_matches(
                    db,
                    store_id=store_id,
                    embedding=embedding,
                    exclude_camera_id=camera_id,
                )

        if matches:
            logger.info(
                "reid_cross_camera_matches alert_id=%s camera_id=%s matches=%d",
                alert_id,
                camera_id,
                len(matches),
            )

        return matches


# Module-level singleton
reid_service = ReIDService()

"""Cross-camera Re-Identification service.

Extracts 576-dim appearance embeddings from person crops using
MobileNetV3-Small (torchvision, already in requirements). Embeddings are
L2-normalised and stored in the `person_embeddings` pgvector table.
Cosine similarity search finds the same person across cameras within the
same store and a configurable time window.

Architecture notes:
  - Model is lazy-loaded on first alert; never blocks the inference loop.
  - Embedding extraction is synchronous (CPU, ~5ms per crop) and called
    from the AI thread via executor.
  - DB writes and Re-ID queries are async; both run on the main event loop
    via `camera_manager._submit_async` (the same pattern as health reports).
  - Disabled gracefully when torch/torchvision are not installed.
"""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)

REID_EMBEDDING_DIM = 576
REID_MATCH_THRESHOLD = 0.75  # cosine similarity ≥ this → same person
REID_WINDOW_MINUTES = 30      # search window: last N minutes per store


class ReIDService:
    """Singleton Re-ID service — lazy model load, thread-safe."""

    def __init__(self) -> None:
        self._model = None
        self._transform = None
        self._lock = threading.Lock()
        self._enabled: bool | None = None  # None = not yet tried
        self._device: str = "cpu"

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load MobileNetV3-Small feature extractor (no classifier)."""
        try:
            import torch
            import torchvision.models as tvm
            import torchvision.transforms as T

            weights = tvm.MobileNet_V3_Small_Weights.IMAGENET1K_V1
            model = tvm.mobilenet_v3_small(weights=weights)
            # Replace classifier with identity → forward() returns 576-dim features
            import torch.nn as nn
            model.classifier = nn.Identity()
            model.eval()

            self._device = (
                "cuda" if torch.cuda.is_available()
                else "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
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
    # Embedding extraction
    # ------------------------------------------------------------------

    def extract_embedding(
        self,
        frame: "np.ndarray",
        bbox: list[float],
    ) -> "np.ndarray | None":
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
            # Guard against degenerate boxes
            x1, x2 = max(0, x1), min(frame.shape[1], x2)
            y1, y2 = max(0, y1), min(frame.shape[0], y2)
            if x2 - x1 < 8 or y2 - y1 < 8:
                return None

            crop = frame[y1:y2, x1:x2]
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(crop_rgb)

            tensor = self._transform(img).unsqueeze(0).to(self._device)

            with torch.no_grad():
                feat = model(tensor)          # (1, 576)
                feat = feat.squeeze(0)        # (576,)
                feat = feat / (feat.norm() + 1e-8)  # L2 normalise

            return feat.cpu().float().numpy()
        except Exception as exc:
            logger.debug("reid_embedding_failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Async DB helpers
    # ------------------------------------------------------------------

    async def store_embedding(
        self,
        db,
        *,
        store_id: int,
        camera_id: int,
        track_id: int,
        embedding: "np.ndarray",
        bbox: list[float],
        alert_id: int | None = None,
        captured_at: datetime | None = None,
    ) -> int | None:
        """Persist an embedding and return its row id."""
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

    async def find_cross_camera_matches(
        self,
        db,
        *,
        store_id: int,
        embedding: "np.ndarray",
        exclude_camera_id: int,
        threshold: float = REID_MATCH_THRESHOLD,
        since_minutes: int = REID_WINDOW_MINUTES,
        limit: int = 5,
    ) -> list[dict]:
        """Return top-k matches from OTHER cameras in the same store.

        Returns a list of dicts:
            camera_id, alert_id, track_id, similarity,
            bbox_x1/y1/x2/y2, captured_at
        sorted by descending similarity.
        """
        from sqlalchemy import text

        since = datetime.now(UTC) - timedelta(minutes=since_minutes)

        try:
            result = await db.execute(
                text(
                    """
                    SELECT
                        id,
                        camera_id,
                        alert_id,
                        track_id,
                        1 - (embedding <=> :embedding::vector) AS similarity,
                        bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                        captured_at
                    FROM person_embeddings
                    WHERE store_id     = :store_id
                      AND camera_id   != :exclude_camera_id
                      AND captured_at >= :since
                      AND 1 - (embedding <=> :embedding::vector) >= :threshold
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

    async def process_alert_embedding(
        self,
        *,
        frame: "np.ndarray",
        bbox: list[float],
        store_id: int,
        camera_id: int,
        track_id: int,
        alert_id: int,
    ) -> list[dict]:
        """Extract embedding, store it, and search for cross-camera matches.

        Called from the alert dispatch path (AI inference thread) via
        camera_manager._submit_async. Returns the match list so callers
        can attach it to the alert payload for the UI.

        All DB work is done inside a single session obtained here so this
        async function can be submitted directly to the main event loop.
        """
        from app.core.tenancy_context import system_bypass
        from app.db.session import AsyncSessionLocal

        embedding = self.extract_embedding(frame, bbox)
        if embedding is None:
            return []

        with system_bypass():
            async with AsyncSessionLocal() as db:
                await self.store_embedding(
                    db,
                    store_id=store_id,
                    camera_id=camera_id,
                    track_id=track_id,
                    embedding=embedding,
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

"""Text embedding service for the RAG layer.

Wraps `sentence-transformers` so the rest of the app never imports it
directly. The model is loaded lazily on first use (multilingual-e5 is
~470MB / ~120MB for the small variant) and cached at module level so the
detection loop and the corpus CRUD endpoints share one tensor copy.

Why multilingual-e5: store policy docs and alert descriptions in this
project arrive in Mongolian + English. e5 is the documented retrieval
model that handles both with a single tokenizer; using two language-
specific models would double the memory footprint without measurable
recall gains for our short snippets.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


_model: "SentenceTransformer | None" = None
_model_lock = threading.Lock()


# e5 was trained with explicit "query:"/"passage:" prefixes — using them
# is non-optional for good retrieval recall. Callers pick the role via
# the public API instead of having to remember the magic string.
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


def _get_model() -> "SentenceTransformer":
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        logger.info(
            "Loading embedding model %s on %s",
            settings.RAG_MODEL_NAME,
            settings.RAG_DEVICE,
        )
        _model = SentenceTransformer(
            settings.RAG_MODEL_NAME, device=settings.RAG_DEVICE
        )
        return _model


def embedding_dimension() -> int:
    """Vector size for the configured model.

    Used by the Qdrant collection bootstrap; calling it before the first
    embed forces a model load, so prefer reading it once at startup.
    """
    return int(_get_model().get_sentence_embedding_dimension())


def _encode_sync(texts: list[str], *, prefix: str) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    prefixed = [prefix + t for t in texts]
    vectors = model.encode(
        prefixed,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


async def embed_query(text: str) -> list[float]:
    """Embed a single query string (alert description, user search)."""
    vectors = await asyncio.to_thread(_encode_sync, [text], prefix=_QUERY_PREFIX)
    return vectors[0]


async def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed corpus passages (store policy docs, historical alerts)."""
    return await asyncio.to_thread(_encode_sync, texts, prefix=_PASSAGE_PREFIX)


async def embed_passage(text: str) -> list[float]:
    vectors = await embed_passages([text])
    return vectors[0]

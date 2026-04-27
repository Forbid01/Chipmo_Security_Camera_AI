"""Postgres + pgvector retrieval for the alert suppression layer.

Replaces the previous Qdrant-backed implementation. The vectors live
inside the same Postgres instance as the rest of the app data, indexed
via HNSW for cosine distance. There is no second service to provision,
no second connection pool to manage, and no second backup pipeline.

A single retriever module orchestrates upserts (when an admin uploads
a policy / known-FP doc) and queries (when classifying a fresh alert).
Tenant safety: every query has `WHERE store_id = :store_id` baked in
so a regression here cannot leak one tenant's docs into another's
verdict.

Cost / latency notes:
  - Embedding (multilingual-e5-small, CPU): ~50ms per text on Railway
    Pro tier, dominated by tokenization.
  - HNSW search (10K rows): ~5-15ms.
  - Total RAG eval per alert: ~70-100ms — well under the 500ms VLM
    budget that gates the dispatch path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.db.models.rag_corpus import RAG_EMBEDDING_DIM, RagCorpusDocument
from app.services import embedding_service
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class RetrievedDoc:
    id: int
    score: float  # cosine similarity in [0, 1]; higher = more similar
    text: str
    doc_type: str
    metadata: dict[str, Any]


@dataclass
class RagDecision:
    """Verdict the orchestrator hands to the alert pipeline.

    `should_suppress` is the only field the alert path strictly needs;
    `top_docs` and `fp_score` are persisted in `suppressed_reason` so
    operators can audit *why* a real alert got dropped.
    """

    should_suppress: bool
    fp_score: float
    top_docs: list[RetrievedDoc]
    reason: str


def assert_dim(vec: list[float]) -> list[float]:
    """Guard against silent dim mismatches when an embedding model
    swap forgets the migration. A vector with the wrong length would
    otherwise INSERT and explode at query time on the index side."""
    if len(vec) != RAG_EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dim {len(vec)} != expected {RAG_EMBEDDING_DIM}. "
            "Run the matching alembic migration before changing models."
        )
    return vec


async def upsert_document(
    db: "AsyncSession",
    *,
    store_id: int,
    doc_type: str,
    text: str,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RagCorpusDocument:
    """Insert a passage and embed it in the same transaction.

    Returns the persisted ORM row (with id + embedding populated). The
    caller commits — keeps tenancy/RLS context attached to the same
    session that's already pinned per-request.
    """
    vector = await embedding_service.embed_passage(text)
    assert_dim(vector)

    doc = RagCorpusDocument(
        store_id=store_id,
        doc_type=doc_type,
        title=title,
        content=text,
        embedding=vector,
        extra_metadata=metadata,
    )
    db.add(doc)
    await db.flush()  # populates `id` without committing
    return doc


async def delete_document(db: "AsyncSession", doc: RagCorpusDocument) -> None:
    await db.delete(doc)


async def retrieve(
    db: "AsyncSession",
    *,
    store_id: int,
    query_text: str,
    top_k: int | None = None,
    doc_types: list[str] | None = None,
) -> list[RetrievedDoc]:
    """Top-k store-scoped passages by cosine similarity to `query_text`.

    Returns the strongest match first. Rows with NULL embedding (legacy
    Qdrant-era inserts that haven't been backfilled yet) are skipped
    via `IS NOT NULL`.
    """
    vector = await embedding_service.embed_query(query_text)
    assert_dim(vector)
    k = top_k or settings.RAG_TOP_K

    distance = RagCorpusDocument.embedding.cosine_distance(vector)
    stmt = (
        select(RagCorpusDocument, distance.label("distance"))
        .where(
            RagCorpusDocument.store_id == store_id,
            RagCorpusDocument.embedding.is_not(None),
        )
        .order_by("distance")
        .limit(k)
    )
    if doc_types:
        stmt = stmt.where(RagCorpusDocument.doc_type.in_(doc_types))

    result = await db.execute(stmt)
    rows = result.all()

    out: list[RetrievedDoc] = []
    for row in rows:
        doc, dist = row
        # pgvector returns cosine distance in [0, 2]. Convert to
        # similarity in [0, 1] so the threshold semantics match the
        # previous Qdrant implementation (1 - cos_distance/2 maps the
        # full range; for normalized vectors cosine distance is in
        # [0, 2] but typical semantic matches sit in [0, 1.5]).
        similarity = max(0.0, min(1.0, 1.0 - float(dist) / 2.0))
        out.append(
            RetrievedDoc(
                id=int(doc.id),
                score=similarity,
                text=doc.content,
                doc_type=doc.doc_type,
                metadata=doc.extra_metadata or {},
            )
        )
    return out


async def evaluate_alert(
    db: "AsyncSession",
    *,
    store_id: int,
    alert_description: str,
    fp_threshold: float,
) -> RagDecision:
    """Score an alert against the store's known-FP corpus.

    Falls back to a passing verdict when the corpus is empty or any
    layer raises — see rag_vlm_pipeline for the matching error swallow
    on the orchestrator side. We'd rather over-alert than silently
    drop a real shoplifting incident due to a vector store hiccup.
    """
    docs = await retrieve(
        db,
        store_id=store_id,
        query_text=alert_description,
        doc_types=["known_fp"],
        top_k=settings.RAG_TOP_K,
    )

    if not docs:
        return RagDecision(
            should_suppress=False,
            fp_score=0.0,
            top_docs=[],
            reason="no known_fp corpus for store",
        )

    top = docs[0]
    fp_score = top.score
    suppress = fp_score >= fp_threshold
    reason = (
        f"matches known_fp #{top.id} (score={fp_score:.2f} >= {fp_threshold:.2f})"
        if suppress
        else f"top match score {fp_score:.2f} below threshold {fp_threshold:.2f}"
    )
    return RagDecision(
        should_suppress=suppress,
        fp_score=fp_score,
        top_docs=docs,
        reason=reason,
    )

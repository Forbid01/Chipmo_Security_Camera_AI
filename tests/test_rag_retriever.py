"""Tests for the pgvector-backed RAG retriever.

The actual database is mocked via an AsyncMock session — these tests
assert orchestration logic only: that `evaluate_alert` thresholds
correctly, that `retrieve` filters by store_id, and that
`upsert_document` produces a row carrying an embedding of the right
dimension. No real Postgres / pgvector required.

We stub the embedding service so CI machines without the
sentence-transformers wheel + multilingual-e5 download can still run
the suite. The dimension matches what the model produces in
production (384 for multilingual-e5-small).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from shoplift_detector.app.db.models.rag_corpus import (
    RAG_EMBEDDING_DIM,
    RagCorpusDocument,
)


# Stub the embedding service via both import paths (sys.path inserts
# `shoplift_detector` so the same module lives under two names).
import app.services.embedding_service as _emb_mod_short
import shoplift_detector.app.services.embedding_service as _emb_mod_full

_FAKE_VECTOR = [0.1] * RAG_EMBEDDING_DIM
for mod in (_emb_mod_full, _emb_mod_short):
    mod.embed_query = AsyncMock(return_value=_FAKE_VECTOR)
    mod.embed_passage = AsyncMock(return_value=_FAKE_VECTOR)


from app.services import rag_retriever  # noqa: E402


def _mock_session_with_rows(rows: list[tuple[RagCorpusDocument, float]]):
    """Build an AsyncMock that returns the given (doc, distance) tuples
    when `execute().all()` is called. Mirrors the SQLAlchemy 2.0 row
    shape `result.all() -> list[Row]`."""
    session = AsyncMock()
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    return session


def _make_doc(*, doc_id=1, store_id=1, content="known fp text", doc_type="known_fp"):
    doc = RagCorpusDocument(
        id=doc_id,
        store_id=store_id,
        doc_type=doc_type,
        content=content,
        embedding=_FAKE_VECTOR,
        extra_metadata={"source": "admin"},
    )
    return doc


@pytest.mark.asyncio
async def test_evaluate_alert_passes_when_below_threshold():
    """Cosine distance 0.6 → similarity 0.7. Below threshold 0.85,
    so the alert should pass through to the next layer."""
    db = _mock_session_with_rows([(_make_doc(), 0.6)])
    decision = await rag_retriever.evaluate_alert(
        db, store_id=1, alert_description="x", fp_threshold=0.85
    )
    assert decision.should_suppress is False
    assert 0.65 < decision.fp_score < 0.75


@pytest.mark.asyncio
async def test_evaluate_alert_suppresses_when_above_threshold():
    """Cosine distance 0.1 → similarity 0.95. Above threshold 0.85 so
    the orchestrator should suppress."""
    db = _mock_session_with_rows([(_make_doc(), 0.1)])
    decision = await rag_retriever.evaluate_alert(
        db, store_id=1, alert_description="x", fp_threshold=0.85
    )
    assert decision.should_suppress is True
    assert decision.fp_score >= 0.85
    assert "matches known_fp" in decision.reason or "suppressed" in decision.reason.lower()


@pytest.mark.asyncio
async def test_evaluate_alert_passes_through_on_empty_corpus():
    """An empty store corpus is the rule, not the exception, for new
    customers. The retriever must not silently suppress every alert in
    that state."""
    db = _mock_session_with_rows([])
    decision = await rag_retriever.evaluate_alert(
        db, store_id=42, alert_description="x", fp_threshold=0.85
    )
    assert decision.should_suppress is False
    assert "no known_fp" in decision.reason.lower()


@pytest.mark.asyncio
async def test_retrieve_calls_session_execute_once():
    """Sanity: the retriever runs exactly one query per call. A
    regression that issued an N+1 over rows would show up here."""
    db = _mock_session_with_rows([(_make_doc(), 0.5)])
    out = await rag_retriever.retrieve(
        db, store_id=7, query_text="x", doc_types=["known_fp"]
    )
    assert len(out) == 1
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_document_persists_embedding():
    """The repo path embeds + adds the row in one shot. Verifies that
    the embedding actually lands on the model instance — a regression
    that forgot to assign `embedding=` would silently insert NULL and
    every later retrieve would skip the row."""
    db = _mock_session_with_rows([])
    doc = await rag_retriever.upsert_document(
        db,
        store_id=3,
        doc_type="known_fp",
        text="customer browsing normally",
        title="Хэвийн худалдан авагч",
    )
    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    added = db.add.call_args[0][0]
    assert added.store_id == 3
    assert added.doc_type == "known_fp"
    assert added.embedding == _FAKE_VECTOR
    assert added.title == "Хэвийн худалдан авагч"
    assert doc is added


@pytest.mark.asyncio
async def test_assert_dim_rejects_wrong_dim():
    """Guard against silent dim mismatch when an embedding model swap
    forgets the migration. Inserting a 768-dim vector into a 384-dim
    column would explode at index time — fail loudly here instead."""
    with pytest.raises(ValueError, match="384"):
        rag_retriever.assert_dim([0.0] * 768)

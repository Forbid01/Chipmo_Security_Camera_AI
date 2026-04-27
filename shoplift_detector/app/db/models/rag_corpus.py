from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .store import Store

# Doc types kept as plain strings (no enum) so a future stage can ship a
# new category without a schema migration. The retriever filter relies
# on these constants — keep them in sync with rag_retriever.py.
RAG_DOC_TYPES = ("policy", "known_fp", "incident_note")

# Embedding dimension matches `intfloat/multilingual-e5-small`. Changing
# the embedding model requires a new migration that ALTERs the column
# (vector type is not nullable-flexible on dim).
RAG_EMBEDDING_DIM = 384


def _vector_column_type():
    """Return the SQLAlchemy column type for the embedding.

    Imports pgvector lazily so the model module loads in environments
    that don't have the package installed (CI without the optional
    extra, SQLite-backed unit tests). Falls back to a plain JSON column
    when pgvector is unavailable so model imports never crash; the
    retriever guards against this case too.
    """
    try:
        from pgvector.sqlalchemy import Vector

        return Vector(RAG_EMBEDDING_DIM)
    except ImportError:
        return JSON


class RagCorpusDocument(Base):
    """One passage in the per-store retrieval corpus.

    The vector lives in the `embedding` column (pgvector). The SQL row
    *is* the source of truth — there is no second store to keep in
    sync, which removes a class of "Postgres has it but the vector DB
    doesn't" bugs we'd see with a separate Qdrant deployment.
    """

    __tablename__ = "rag_corpus"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # `embedding` is nullable because rows created by the legacy
    # 20260427_01 migration (Qdrant era) carry no vector. The repo
    # backfills it on the next write; the retriever skips NULL rows.
    embedding: Mapped[list[float] | None] = mapped_column(
        _vector_column_type(), nullable=True
    )
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    store: Mapped[Optional["Store"]] = relationship()

    def __repr__(self) -> str:
        return (
            f"<RagCorpusDocument(id={self.id}, store_id={self.store_id}, "
            f"type='{self.doc_type}')>"
        )

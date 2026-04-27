"""Repository for the RAG corpus SQL records.

Pgvector keeps the vector inside the same table as the SQL row, so
this layer is a thin wrapper around the ORM. The retriever embeds the
content during `create()` so callers don't have to think about
vectors at all — they hand in title + content and get back a row that
is immediately searchable.
"""

from typing import Any

from app.db.models.rag_corpus import RagCorpusDocument
from app.services import rag_retriever
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class RagCorpusRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_store(
        self,
        store_id: int,
        *,
        doc_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RagCorpusDocument]:
        stmt = select(RagCorpusDocument).where(
            RagCorpusDocument.store_id == store_id
        )
        if doc_type:
            stmt = stmt.where(RagCorpusDocument.doc_type == doc_type)
        stmt = (
            stmt.order_by(RagCorpusDocument.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, doc_id: int) -> RagCorpusDocument | None:
        result = await self.db.execute(
            select(RagCorpusDocument).where(RagCorpusDocument.id == doc_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        store_id: int,
        doc_type: str,
        content: str,
        title: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> RagCorpusDocument:
        # The retriever embeds + adds the row to the session. We
        # commit here so the API contract remains "after this returns,
        # the doc is searchable".
        doc = await rag_retriever.upsert_document(
            self.db,
            store_id=store_id,
            doc_type=doc_type,
            text=content,
            title=title,
            metadata=extra_metadata,
        )
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def delete(self, doc: RagCorpusDocument) -> None:
        await rag_retriever.delete_document(self.db, doc)
        await self.db.commit()

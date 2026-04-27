"""RAG corpus management endpoints.

Admins upload store-scoped documents (policy, known_fp, incident_note)
that the alert pipeline consults at decision time. Tenant isolation
goes through `require_store_access` — the same dependency used by every
other store-scoped route in the v1 API.
"""

from typing import Annotated

from app.core.security import AdminOrAbove
from app.core.tenancy import require_store_access
from app.db.repository.rag_corpus_repo import RagCorpusRepository
from app.db.session import DB
from app.schemas.common import APIResponse
from app.schemas.rag_corpus import RagDocumentCreate, RagDocumentResponse
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/stores/{store_id}/rag-corpus", response_model=list[RagDocumentResponse])
async def list_rag_corpus(
    store_id: int,
    db: DB,
    store: Annotated[dict, Depends(require_store_access)],
    doc_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    repo = RagCorpusRepository(db)
    docs = await repo.list_for_store(
        store_id, doc_type=doc_type, limit=limit, offset=offset
    )
    return docs


@router.post("/stores/{store_id}/rag-corpus", response_model=RagDocumentResponse)
async def create_rag_corpus(
    store_id: int,
    payload: RagDocumentCreate,
    admin: AdminOrAbove,
    db: DB,
    store: Annotated[dict, Depends(require_store_access)],
):
    repo = RagCorpusRepository(db)
    doc = await repo.create(
        store_id=store_id,
        doc_type=payload.doc_type,
        content=payload.content,
        title=payload.title,
        extra_metadata=payload.extra_metadata,
    )
    return doc


@router.delete("/rag-corpus/{doc_id}", response_model=APIResponse)
async def delete_rag_corpus(
    doc_id: int,
    admin: AdminOrAbove,
    db: DB,
):
    repo = RagCorpusRepository(db)
    doc = await repo.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Баримт олдсонгүй")

    # Tenant guard — reuse require_store_access by hand because the
    # path is doc-scoped, not store-scoped.
    if admin.get("role") != "super_admin":
        if doc.store_id is None:
            raise HTTPException(status_code=404, detail="Баримт олдсонгүй")
        await require_store_access(doc.store_id, admin, db)

    await repo.delete(doc)
    return APIResponse(message="Баримт устгагдлаа")

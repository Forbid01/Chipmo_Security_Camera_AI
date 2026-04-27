"""Pydantic schemas for the RAG corpus API.

`doc_type` is restricted at schema level so the OpenAPI contract is the
documentation; the SQL column itself stays a plain VARCHAR (see
db/models/rag_corpus.py) to allow new types without a migration.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DocType = Literal["policy", "known_fp", "incident_note"]


class RagDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: DocType
    title: str | None = Field(default=None, max_length=200)
    content: str = Field(..., min_length=1, max_length=10_000)
    extra_metadata: dict[str, Any] | None = None


class RagDocumentResponse(BaseModel):
    id: int
    store_id: int
    doc_type: str
    title: str | None
    content: str
    qdrant_point_id: str | None
    extra_metadata: dict[str, Any] | None
    created_at: Any
    updated_at: Any

    model_config = ConfigDict(from_attributes=True)

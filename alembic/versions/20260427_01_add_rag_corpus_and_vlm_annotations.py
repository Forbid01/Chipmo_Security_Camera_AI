"""Add rag_corpus and vlm_annotations tables.

Phase 1/2 of the RAG + Qwen2.5-VL integration. Both tables are
strictly additive — existing alerts, stores, and feedback rows are
untouched. The vector data itself lives in Qdrant; `rag_corpus` is the
SQL system of record (so admins can edit / list / delete docs) and
holds `qdrant_point_id` to link the two.

`vlm_annotations` is one-to-one with alerts (ON DELETE CASCADE) so a
deleted alert takes its VLM caption with it; a UNIQUE on alert_id
keeps the relation 1:1.

Revision ID: 20260427_01
Revises: 20260424_05
"""

from alembic import op

revision = "20260427_01"
down_revision = "20260424_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_corpus (
            id              SERIAL PRIMARY KEY,
            store_id        INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
            doc_type        VARCHAR(32) NOT NULL,
            title           TEXT,
            content         TEXT NOT NULL,
            qdrant_point_id VARCHAR(64),
            extra_metadata  JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_rag_corpus_store
            ON rag_corpus (store_id);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_rag_corpus_doc_type
            ON rag_corpus (store_id, doc_type);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vlm_annotations (
            id          SERIAL PRIMARY KEY,
            alert_id    INTEGER NOT NULL UNIQUE REFERENCES alerts(id) ON DELETE CASCADE,
            model_name  VARCHAR(128) NOT NULL,
            caption     TEXT,
            confidence  DOUBLE PRECISION,
            reasoning   JSONB,
            latency_ms  INTEGER,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_vlm_annotations_alert
            ON vlm_annotations (alert_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vlm_annotations_alert;")
    op.execute("DROP TABLE IF EXISTS vlm_annotations CASCADE;")
    op.execute("DROP INDEX IF EXISTS ix_rag_corpus_doc_type;")
    op.execute("DROP INDEX IF EXISTS ix_rag_corpus_store;")
    op.execute("DROP TABLE IF EXISTS rag_corpus CASCADE;")

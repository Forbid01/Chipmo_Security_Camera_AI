"""Switch RAG retrieval from Qdrant to pgvector.

The previous migration (20260427_01) created a SQL `rag_corpus` table
with a `qdrant_point_id` column that linked to vectors stored in a
separate Qdrant service. This migration moves the vectors *into*
Postgres via the pgvector extension so we can drop the Qdrant
dependency entirely on Railway-style deployments.

Why pgvector:
  - Railway's managed Postgres ships with the extension already
    available, so no infra change is needed beyond `CREATE EXTENSION`.
  - One service (Postgres) instead of two (Postgres + Qdrant). One
    backup pipeline, one connection pool, one tenant isolation story.
  - At our expected scale (≤100K passages per tenant) HNSW search
    inside Postgres is well under 50ms — fast enough for the alert
    dispatch path.

Changes:
  - CREATE EXTENSION vector (idempotent).
  - ADD `embedding vector(384)` to `rag_corpus`. 384 is the dimension
    of `intfloat/multilingual-e5-small`; if we ever swap the embedding
    model the new dim has to land in a follow-up migration.
  - ADD HNSW index for cosine distance.
  - DROP `qdrant_point_id` (the new vector column subsumes it).

Revision ID: 20260427_02
Revises: 20260427_01
"""

from alembic import op

revision = "20260427_02"
down_revision = "20260427_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS keeps the migration idempotent on databases where
    # the extension is already installed (Qdrant Cloud-style preinstall,
    # or repeat-deploys against the same DB).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Embedding column. Nullable so existing rows from migration
    # 20260427_01 stay readable; the repo backfills lazily on next write.
    op.execute(
        """
        ALTER TABLE rag_corpus
            ADD COLUMN IF NOT EXISTS embedding vector(384);
        """
    )

    # HNSW index — much faster than the default exact scan once the
    # corpus reaches a few hundred rows. m / ef_construction left at
    # pgvector defaults (16 / 64); tune later if recall regresses.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_rag_corpus_embedding
            ON rag_corpus USING hnsw (embedding vector_cosine_ops);
        """
    )

    # qdrant_point_id is no longer the source of truth — the embedding
    # is the source of truth now. Dropping the column avoids drift
    # where someone re-implements Qdrant integration and the two stores
    # disagree.
    op.execute(
        """
        ALTER TABLE rag_corpus DROP COLUMN IF EXISTS qdrant_point_id;
        """
    )


def downgrade() -> None:
    # Re-add qdrant_point_id (nullable) so a rollback to the Qdrant
    # implementation can repopulate it. The vectors themselves can't
    # be reconstructed in a downgrade — operators would need to
    # re-embed against the chosen Qdrant collection.
    op.execute(
        """
        ALTER TABLE rag_corpus ADD COLUMN IF NOT EXISTS qdrant_point_id VARCHAR(64);
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_rag_corpus_embedding;")
    op.execute("ALTER TABLE rag_corpus DROP COLUMN IF EXISTS embedding;")
    # Intentionally keep the extension installed on downgrade — it's
    # cheap and other tables may depend on it.

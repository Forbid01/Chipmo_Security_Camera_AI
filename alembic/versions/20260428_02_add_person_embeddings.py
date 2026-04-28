"""Add person_embeddings table for cross-camera Re-ID.

Stores 576-dim appearance embeddings extracted from person crops at alert
time. pgvector HNSW index enables sub-millisecond cosine similarity search
across cameras within the same store.

Why 576-dim: MobileNetV3-Small (already in torchvision, no extra deps)
outputs 576-dim feature vectors after global average pooling. L2-normalized
before storage so cosine distance == euclidean distance, compatible with
both `<=>` and `<->` operators.

Revision ID: 20260428_02
Revises: 20260428_01
"""

from alembic import op

revision = "20260428_02"
down_revision = "20260428_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector should already be installed from 20260427_02, but guard
    # idempotently in case this migration runs against a fresh DB.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS person_embeddings (
            id          BIGSERIAL PRIMARY KEY,
            store_id    INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
            camera_id   INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            alert_id    INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
            track_id    INTEGER NOT NULL,
            embedding   vector(576) NOT NULL,
            bbox_x1     FLOAT,
            bbox_y1     FLOAT,
            bbox_x2     FLOAT,
            bbox_y2     FLOAT,
            captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pe_store_id  ON person_embeddings (store_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pe_camera_id ON person_embeddings (camera_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pe_captured_at ON person_embeddings (captured_at DESC);"
    )
    # HNSW for fast approximate cosine search across all embeddings in a store.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pe_embedding
            ON person_embeddings USING hnsw (embedding vector_cosine_ops);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS person_embeddings;")

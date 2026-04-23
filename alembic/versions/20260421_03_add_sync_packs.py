"""add sync_packs table

Revision ID: 20260421_03
Revises: 20260421_01
Create Date: 2026-04-21 00:00:00

- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `store_id INTEGER NOT NULL REFERENCES stores(id)`
- Status values locked to: pending/downloaded/applied/failed/rolled_back

Additive, safe to deploy before sync APIs exist. Rollback-safe downgrade.
"""

from alembic import op

revision = "20260421_03"
down_revision = "20260421_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE TABLE IF NOT EXISTS sync_packs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,

            version VARCHAR(32) NOT NULL,

            weights_hash VARCHAR(64),
            qdrant_snapshot_id VARCHAR(128),
            case_count INTEGER,

            s3_path VARCHAR(500),
            signature VARCHAR(255),

            status VARCHAR(32) NOT NULL DEFAULT 'pending',

            applied_at TIMESTAMPTZ,

            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT ck_sync_packs_status CHECK (
                status IN ('pending', 'downloaded', 'applied', 'failed', 'rolled_back')
            ),

            CONSTRAINT uq_sync_packs_store_version UNIQUE (store_id, version)
        );

        CREATE INDEX IF NOT EXISTS idx_sync_packs_store
            ON sync_packs (store_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_sync_packs_active
            ON sync_packs (store_id, status)
            WHERE status IN ('pending', 'downloaded', 'applied');
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS sync_packs;
    """)

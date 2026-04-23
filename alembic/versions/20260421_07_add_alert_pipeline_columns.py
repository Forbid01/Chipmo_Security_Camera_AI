"""add RAG/VLM pipeline columns to alerts

Revision ID: 20260421_07
Revises: 20260421_06
Create Date: 2026-04-21 00:00:00

Per docs/07-SCHEMA-MIGRATION-LOCK.md §7.6 (allowed additive columns on
`alerts`). All new columns are nullable or have a default so:

- Existing rows remain readable with no backfill.
- Legacy code paths that SELECT * still work (the new columns surface
  as None / False).
- Legacy INSERT paths that omit the new columns still succeed.

Indexes follow docs/06-DATABASE-SCHEMA.md §3:
- `idx_alerts_suppressed` — partial index on (store_id, event_time) for
  the common "show me non-suppressed alerts" query shape.

Rollback: drop the indexes, then the columns. Existing production data
survives the rollback because the new columns are additive.
"""

from alembic import op

revision = "20260421_07"
down_revision = "20260421_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE alerts
            ADD COLUMN IF NOT EXISTS suppressed BOOLEAN NOT NULL DEFAULT FALSE;

        ALTER TABLE alerts
            ADD COLUMN IF NOT EXISTS suppressed_reason TEXT;

        ALTER TABLE alerts
            ADD COLUMN IF NOT EXISTS rag_decision VARCHAR(32);

        ALTER TABLE alerts
            ADD COLUMN IF NOT EXISTS vlm_decision VARCHAR(32);

        ALTER TABLE alerts
            ADD COLUMN IF NOT EXISTS person_track_id INTEGER;

        CREATE INDEX IF NOT EXISTS idx_alerts_suppressed
            ON alerts (store_id, event_time DESC)
            WHERE suppressed = FALSE;

        CREATE INDEX IF NOT EXISTS idx_alerts_person_track
            ON alerts (camera_id, person_track_id)
            WHERE person_track_id IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_alerts_person_track;
        DROP INDEX IF EXISTS idx_alerts_suppressed;

        ALTER TABLE alerts DROP COLUMN IF EXISTS person_track_id;
        ALTER TABLE alerts DROP COLUMN IF EXISTS vlm_decision;
        ALTER TABLE alerts DROP COLUMN IF EXISTS rag_decision;
        ALTER TABLE alerts DROP COLUMN IF EXISTS suppressed_reason;
        ALTER TABLE alerts DROP COLUMN IF EXISTS suppressed;
    """)

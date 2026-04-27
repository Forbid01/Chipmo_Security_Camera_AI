"""add cameras.shelf_zones JSONB column

Revision ID: 20260423_01
Revises: 20260422_07
Create Date: 2026-04-23 00:00:00

Per-camera shelf ROI polygons so the AI service can detect "hand-into-shelf"
interactions without relying on COCO object classes (which miss >80% of
real retail inventory like grocery, apparel, cosmetics).

Schema: JSONB array of zone objects, each with normalized 0..1 coords so
zones are resolution-independent and survive camera resolution changes.

  [
    {
      "id": "uuid-string",
      "name": "Beer fridge",
      "polygon": [[0.12, 0.34], [0.56, 0.34], [0.56, 0.78], [0.12, 0.78]]
    }
  ]

Additive, nullable on expand per docs/07-SCHEMA-MIGRATION-LOCK.md.
Default [] means cameras with no zones fall back to legacy COCO detection.
"""

from alembic import op

revision = "20260423_01"
down_revision = "20260422_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'cameras'
                  AND column_name = 'shelf_zones'
            ) THEN
                ALTER TABLE cameras
                    ADD COLUMN shelf_zones JSONB NOT NULL DEFAULT '[]'::jsonb;
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_cameras_shelf_zones_gin
            ON cameras USING GIN (shelf_zones);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_cameras_shelf_zones_gin;
        ALTER TABLE cameras DROP COLUMN IF EXISTS shelf_zones;
    """)

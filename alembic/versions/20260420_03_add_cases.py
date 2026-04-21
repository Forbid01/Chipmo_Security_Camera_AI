"""add cases metadata table

Revision ID: 20260420_03
Revises: 20260420_02
Create Date: 2026-04-20 00:00:00
"""

from alembic import op

revision = "20260420_03"
down_revision = "20260420_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE TABLE IF NOT EXISTS cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
            store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
            camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),

            behavior_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
            pose_sequence_path VARCHAR(500),
            clip_path VARCHAR(500),
            keyframe_paths JSONB NOT NULL DEFAULT '[]'::jsonb,

            label VARCHAR(32) NOT NULL DEFAULT 'unlabeled',
            label_confidence DOUBLE PRECISION,
            labeled_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            labeled_at TIMESTAMPTZ,

            vlm_is_suspicious BOOLEAN,
            vlm_confidence DOUBLE PRECISION,
            vlm_reason TEXT,
            vlm_run_at TIMESTAMPTZ,

            qdrant_point_id UUID UNIQUE,

            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT ck_cases_label CHECK (
                label IN ('theft', 'false_positive', 'not_sure', 'unlabeled')
            )
        );

        CREATE INDEX IF NOT EXISTS idx_cases_store_time
            ON cases (store_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_cases_alert_id
            ON cases (alert_id);
        CREATE INDEX IF NOT EXISTS idx_cases_label
            ON cases (store_id, label)
            WHERE label IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_cases_unlabeled
            ON cases (store_id, timestamp DESC)
            WHERE label IS NULL OR label = 'unlabeled';
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS cases;
    """)

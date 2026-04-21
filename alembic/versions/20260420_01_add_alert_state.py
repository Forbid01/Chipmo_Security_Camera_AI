"""add alert_state table

Revision ID: 20260420_01
Revises: 20260416_01
Create Date: 2026-04-20 00:00:00
"""

from alembic import op

revision = "20260420_01"
down_revision = "20260416_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_state (
            id SERIAL PRIMARY KEY,
            camera_id INTEGER NOT NULL DEFAULT 0,
            person_track_id INTEGER NOT NULL,
            state VARCHAR(20) NOT NULL DEFAULT 'idle',
            last_alert_id INTEGER,
            last_alert_at TIMESTAMPTZ,
            cooldown_until TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_alert_state_camera_person UNIQUE (camera_id, person_track_id),
            CONSTRAINT ck_alert_state_state CHECK (
                state IN ('idle', 'active', 'cooldown', 'resolved')
            )
        );

        CREATE INDEX IF NOT EXISTS ix_alert_state_camera_id
            ON alert_state (camera_id);
        CREATE INDEX IF NOT EXISTS ix_alert_state_person_track_id
            ON alert_state (person_track_id);
        CREATE INDEX IF NOT EXISTS ix_alert_state_cooldown_until
            ON alert_state (cooldown_until);

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_alert_state_last_alert_id_alerts'
            ) THEN
                ALTER TABLE alert_state
                    ADD CONSTRAINT fk_alert_state_last_alert_id_alerts
                    FOREIGN KEY (last_alert_id) REFERENCES alerts(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS alert_state;
    """)

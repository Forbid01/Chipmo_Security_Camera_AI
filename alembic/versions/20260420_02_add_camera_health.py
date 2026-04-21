"""add camera_health table

Revision ID: 20260420_02
Revises: 20260420_01
Create Date: 2026-04-20 00:00:00
"""

from alembic import op

revision = "20260420_02"
down_revision = "20260420_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS camera_health (
            camera_id INTEGER PRIMARY KEY,
            store_id INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'offline',
            is_connected BOOLEAN NOT NULL DEFAULT FALSE,
            fps DOUBLE PRECISION NOT NULL DEFAULT 0,
            last_frame_at TIMESTAMPTZ,
            last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            offline_since TIMESTAMPTZ,
            last_error TEXT,
            last_notification_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_camera_health_status CHECK (
                status IN ('online', 'offline', 'degraded')
            )
        );

        CREATE INDEX IF NOT EXISTS ix_camera_health_store_id
            ON camera_health (store_id);
        CREATE INDEX IF NOT EXISTS ix_camera_health_status
            ON camera_health (status);
        CREATE INDEX IF NOT EXISTS ix_camera_health_last_heartbeat_at
            ON camera_health (last_heartbeat_at);
        CREATE INDEX IF NOT EXISTS ix_camera_health_offline_since
            ON camera_health (offline_since);

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_camera_health_camera_id_cameras'
            ) THEN
                ALTER TABLE camera_health
                    ADD CONSTRAINT fk_camera_health_camera_id_cameras
                    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_camera_health_store_id_stores'
            ) THEN
                ALTER TABLE camera_health
                    ADD CONSTRAINT fk_camera_health_store_id_stores
                    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS camera_health;
    """)

"""align railway schema with current app models

Revision ID: 20260414_01
Revises:
Create Date: 2026-04-14 18:35:00
"""


from alembic import op

revision = "20260414_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE alerts
            ADD COLUMN IF NOT EXISTS store_id INTEGER,
            ADD COLUMN IF NOT EXISTS camera_id INTEGER,
            ADD COLUMN IF NOT EXISTS video_path TEXT,
            ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS feedback_status VARCHAR(20);

        UPDATE alerts
        SET feedback_status = CASE
            WHEN COALESCE(reviewed, FALSE) THEN 'reviewed'
            ELSE 'unreviewed'
        END
        WHERE feedback_status IS NULL;

        ALTER TABLE alerts
            ALTER COLUMN feedback_status SET DEFAULT 'unreviewed',
            ALTER COLUMN feedback_status SET NOT NULL;

        ALTER TABLE cameras
            ADD COLUMN IF NOT EXISTS camera_type VARCHAR(20),
            ADD COLUMN IF NOT EXISTS store_id INTEGER,
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN,
            ADD COLUMN IF NOT EXISTS is_ai_enabled BOOLEAN;

        UPDATE cameras
        SET camera_type = COALESCE(camera_type, type, 'rtsp')
        WHERE camera_type IS NULL;

        UPDATE cameras
        SET is_active = COALESCE(is_active, TRUE),
            is_ai_enabled = COALESCE(is_ai_enabled, TRUE)
        WHERE is_active IS NULL OR is_ai_enabled IS NULL;

        ALTER TABLE cameras
            ALTER COLUMN camera_type SET DEFAULT 'rtsp',
            ALTER COLUMN camera_type SET NOT NULL,
            ALTER COLUMN is_active SET DEFAULT TRUE,
            ALTER COLUMN is_active SET NOT NULL,
            ALTER COLUMN is_ai_enabled SET DEFAULT TRUE,
            ALTER COLUMN is_ai_enabled SET NOT NULL;

        CREATE INDEX IF NOT EXISTS ix_alerts_store_id ON alerts (store_id);
        CREATE INDEX IF NOT EXISTS ix_alerts_camera_id ON alerts (camera_id);
        CREATE INDEX IF NOT EXISTS ix_cameras_store_id ON cameras (store_id);
        CREATE INDEX IF NOT EXISTS ix_cameras_organization_id ON cameras (organization_id);

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_alerts_store_id_stores'
            ) THEN
                ALTER TABLE alerts
                    ADD CONSTRAINT fk_alerts_store_id_stores
                    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE SET NULL;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_alerts_camera_id_cameras'
            ) THEN
                ALTER TABLE alerts
                    ADD CONSTRAINT fk_alerts_camera_id_cameras
                    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_cameras_store_id_stores'
            ) THEN
                ALTER TABLE cameras
                    ADD CONSTRAINT fk_cameras_store_id_stores
                    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerts_store_id_stores'
            ) THEN
                ALTER TABLE alerts DROP CONSTRAINT fk_alerts_store_id_stores;
            END IF;

            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerts_camera_id_cameras'
            ) THEN
                ALTER TABLE alerts DROP CONSTRAINT fk_alerts_camera_id_cameras;
            END IF;

            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_cameras_store_id_stores'
            ) THEN
                ALTER TABLE cameras DROP CONSTRAINT fk_cameras_store_id_stores;
            END IF;
        END $$;

        DROP INDEX IF EXISTS ix_alerts_store_id;
        DROP INDEX IF EXISTS ix_alerts_camera_id;
        DROP INDEX IF EXISTS ix_cameras_store_id;

        ALTER TABLE alerts
            DROP COLUMN IF EXISTS store_id,
            DROP COLUMN IF EXISTS camera_id,
            DROP COLUMN IF EXISTS video_path,
            DROP COLUMN IF EXISTS confidence_score,
            DROP COLUMN IF EXISTS feedback_status;

        ALTER TABLE cameras
            DROP COLUMN IF EXISTS camera_type,
            DROP COLUMN IF EXISTS store_id,
            DROP COLUMN IF EXISTS is_active,
            DROP COLUMN IF EXISTS is_ai_enabled;
    """)

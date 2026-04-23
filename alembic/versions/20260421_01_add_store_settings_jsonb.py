"""add stores.settings JSONB column and backfill from legacy columns

Revision ID: 20260421_01
Revises: 20260420_03
Create Date: 2026-04-21 00:00:00

Additive, backward-compatible per docs/07-SCHEMA-MIGRATION-LOCK.md:
- Column is nullable on expand.
- Backfill merges default AI settings with existing per-store
  `alert_threshold` / `alert_cooldown` / `telegram_chat_id` so no store
  silently loses its current tuning.
- Enforcing NOT NULL is deferred to a follow-up migration after the app
  code dual-writes both the new JSONB and legacy columns for one release.
"""

from alembic import op

revision = "20260421_01"
down_revision = "20260420_03"
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
                  AND table_name = 'stores'
                  AND column_name = 'settings'
            ) THEN
                ALTER TABLE stores
                    ADD COLUMN settings JSONB;
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_stores_settings_gin
            ON stores USING GIN (settings);

        UPDATE stores
        SET settings = COALESCE(settings, '{}'::jsonb) || jsonb_build_object(
            'alert_threshold',             COALESCE(alert_threshold, 80.0),
            'alert_cooldown_seconds',      COALESCE(alert_cooldown, 60),
            'night_mode_enabled',          TRUE,
            'night_luminance_threshold',   60.0,
            'dynamic_fps_enabled',         TRUE,
            'fps_idle',                    3,
            'fps_active',                  15,
            'fps_suspicious',              30,
            'clip_retention_normal_h',     48,
            'clip_retention_alert_d',      30,
            'face_blur_enabled',           TRUE,
            'rag_check_enabled',           TRUE,
            'rag_fp_threshold',            0.8,
            'vlm_verification_enabled',    TRUE,
            'vlm_confidence_threshold',    0.5,
            'timezone',                    'Asia/Ulaanbaatar',
            'notification_channels',       jsonb_build_object(
                'telegram', jsonb_build_object(
                    'chat_ids',
                    CASE
                        WHEN telegram_chat_id IS NULL OR telegram_chat_id = ''
                            THEN '[]'::jsonb
                        ELSE jsonb_build_array(telegram_chat_id)
                    END
                ),
                'sms',   jsonb_build_object('numbers',   '[]'::jsonb),
                'email', jsonb_build_object('addresses', '[]'::jsonb)
            )
        )
        WHERE settings IS NULL
           OR NOT (settings ? 'alert_threshold');
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_stores_settings_gin;
        ALTER TABLE stores DROP COLUMN IF EXISTS settings;
    """)

"""Schema repair — bring partial-create_all DBs up to current head.

Some early Railway deploys ran `Base.metadata.create_all` from the
lifespan startup hook but never successfully completed `alembic
upgrade head` (the alembic_version row was empty, so the migration
runner couldn't tell which DDL had landed). The result is a database
where tables defined only in models exist, but tables / columns /
extensions that live exclusively in migrations are missing.

This migration is **fully idempotent** — every statement uses
`IF NOT EXISTS` / `ON CONFLICT DO NOTHING` so it's safe to run on:

  - A pristine production DB (everything already up to date) → no-op
  - A partially-migrated DB (this is the bug case) → fills in the gaps
  - A fresh dev DB just created from `create_all` → adds extension +
    indexes + the four migration-only tables

What it does:
  1. Ensure pgvector extension is installed (the RAG retriever needs it).
  2. Ensure stores.settings (JSONB) + stores.tenant_id (UUID) exist;
     backfill `settings` from the legacy alert_threshold/alert_cooldown
     scalar columns so resolve_settings() doesn't see NULL.
  3. Ensure the four migration-only tables exist with the same shape
     the original migrations defined: `agents`, `store_telegram_subscribers`,
     `alert_escalations`, `push_tokens`.
  4. Ensure the indexes + constraints those migrations created.

Revision ID: 20260427_03
Revises: 20260427_02
"""

from alembic import op

revision = "20260427_03"
down_revision = "20260427_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Extensions
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # gen_random_uuid() lives in pgcrypto — needed by `agents.agent_id`
    # default. pg14+ bundles it in core but the IF NOT EXISTS keeps the
    # statement portable across older managed Postgres images.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # ------------------------------------------------------------------
    # 2. stores — missing columns from migrations 20260421_01 / 20260422_03
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS settings JSONB;")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS tenant_id UUID;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stores_settings_gin "
        "ON stores USING GIN (settings);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stores_tenant "
        "ON stores (tenant_id) WHERE tenant_id IS NOT NULL;"
    )

    # Backfill `settings` from legacy scalar columns. NULL → defaults.
    # Runs once; subsequent runs are no-ops because of the WHERE clause.
    op.execute(
        """
        UPDATE stores
        SET settings = jsonb_build_object(
          'alert_threshold', COALESCE(alert_threshold, 80.0),
          'alert_cooldown_seconds', COALESCE(alert_cooldown, 60),
          'severity_thresholds', jsonb_build_object('yellow', 40.0, 'orange', 70.0, 'red', 85.0),
          'night_mode_enabled', true,
          'night_luminance_threshold', 60.0,
          'dynamic_fps_enabled', true,
          'fps_idle', 3,
          'fps_active', 15,
          'fps_suspicious', 30,
          'clip_retention_normal_h', 48,
          'clip_retention_alert_d', 30,
          'face_blur_enabled', true,
          'rag_check_enabled', true,
          'rag_fp_threshold', 0.8,
          'vlm_verification_enabled', true,
          'vlm_confidence_threshold', 0.5,
          'timezone', 'Asia/Ulaanbaatar',
          'notification_channels', jsonb_build_object(
            'telegram', jsonb_build_object('chat_ids', '[]'::jsonb),
            'sms', jsonb_build_object('numbers', '[]'::jsonb),
            'email', jsonb_build_object('addresses', '[]'::jsonb)
          )
        )
        WHERE settings IS NULL;
        """
    )

    # ------------------------------------------------------------------
    # 3. agents — from migration 20260423_02 (T4-07)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            agent_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            hostname          TEXT NOT NULL,
            platform          TEXT NOT NULL,
            agent_version     TEXT,
            registered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_heartbeat_at TIMESTAMPTZ,
            metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,

            CONSTRAINT agents_platform_valid CHECK (platform IN ('linux', 'windows', 'macos')),
            CONSTRAINT agents_tenant_hostname_unique UNIQUE (tenant_id, hostname)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents (tenant_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agents_last_heartbeat "
        "ON agents (last_heartbeat_at DESC NULLS LAST) "
        "WHERE last_heartbeat_at IS NOT NULL;"
    )

    # ------------------------------------------------------------------
    # 4. store_telegram_subscribers — from migration 20260424_02 (T5-04)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS store_telegram_subscribers (
            id          SERIAL PRIMARY KEY,
            store_id    INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
            chat_id     TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'manager',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT store_telegram_subscribers_role_valid
                CHECK (role IN ('owner', 'manager', 'staff')),
            CONSTRAINT store_telegram_subscribers_unique
                UNIQUE (store_id, chat_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_store_telegram_subscribers_store "
        "ON store_telegram_subscribers (store_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_store_telegram_subscribers_chat "
        "ON store_telegram_subscribers (chat_id);"
    )
    # Backfill from legacy stores.telegram_chat_id singleton.
    op.execute(
        """
        INSERT INTO store_telegram_subscribers (store_id, chat_id, role)
        SELECT id, telegram_chat_id, 'owner'
        FROM stores
        WHERE telegram_chat_id IS NOT NULL AND TRIM(telegram_chat_id) <> ''
        ON CONFLICT (store_id, chat_id) DO NOTHING;
        """
    )

    # ------------------------------------------------------------------
    # 5. alert_escalations — from migration 20260424_04 (T5-09)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_escalations (
            id               SERIAL PRIMARY KEY,
            alert_id         INTEGER NOT NULL,
            channel          TEXT NOT NULL,
            recipient        TEXT,
            delivered_at     TIMESTAMPTZ,
            failed_at        TIMESTAMPTZ,
            error            TEXT,
            acknowledged_by  TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT alert_escalations_channel_valid
                CHECK (channel IN ('telegram', 'email', 'fcm', 'sms')),
            CONSTRAINT alert_escalations_outcome_coherent
                CHECK (
                    (delivered_at IS NOT NULL AND failed_at IS NULL)
                    OR (delivered_at IS NULL AND failed_at IS NOT NULL)
                    OR (delivered_at IS NULL AND failed_at IS NULL)
                )
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_escalations_alert "
        "ON alert_escalations (alert_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_escalations_channel_recent "
        "ON alert_escalations (channel, created_at DESC);"
    )

    # ------------------------------------------------------------------
    # 6. push_tokens — from migration 20260424_05 (T5-07)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS push_tokens (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token       TEXT NOT NULL UNIQUE,
            platform    TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT push_tokens_platform_valid
                CHECK (platform IN ('ios', 'android', 'web'))
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_push_tokens_user ON push_tokens (user_id);"
    )


def downgrade() -> None:
    # This is a repair migration — downgrading would re-introduce the
    # bug it fixed. We keep the down path defined for symmetry but warn
    # operators not to run it without manual review.
    op.execute("DROP TABLE IF EXISTS push_tokens CASCADE;")
    op.execute("DROP TABLE IF EXISTS alert_escalations CASCADE;")
    op.execute("DROP TABLE IF EXISTS store_telegram_subscribers CASCADE;")
    op.execute("DROP TABLE IF EXISTS agents CASCADE;")
    op.execute("DROP INDEX IF EXISTS idx_stores_tenant;")
    op.execute("DROP INDEX IF EXISTS ix_stores_settings_gin;")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS tenant_id;")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS settings;")
    # Extensions intentionally NOT dropped — other code might depend on them.

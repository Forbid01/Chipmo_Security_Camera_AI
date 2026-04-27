"""Add store_telegram_subscribers table (T5-04).

Replaces the legacy singleton `stores.telegram_chat_id` with a
many-to-one table so multiple managers can subscribe to alerts for a
single store. The `role` column gates future per-severity routing
(e.g. send RED only to owners).

Backfill copies any existing non-null `stores.telegram_chat_id` into
the new table with role='owner' so today's single-subscriber stores
keep receiving notifications unchanged. The legacy column is NOT
dropped here — it continues to work as a fallback inside
`ai_service._send_telegram_alert` for as long as T5-04 hasn't been
applied everywhere. Removing the column is a follow-up migration
(T5-07) once the ops audit confirms no writes remain.

Revision ID: 20260424_02
Revises: 20260424_01
"""

from alembic import op

revision = "20260424_02"
down_revision = "20260424_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
        """
        CREATE INDEX IF NOT EXISTS ix_store_telegram_subscribers_store
            ON store_telegram_subscribers (store_id);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_store_telegram_subscribers_chat
            ON store_telegram_subscribers (chat_id);
        """
    )

    # Backfill — copy each store's existing singleton chat_id into the
    # new table with role='owner'. ON CONFLICT keeps the migration
    # idempotent: re-running on a partially-backfilled DB is a no-op.
    op.execute(
        """
        INSERT INTO store_telegram_subscribers (store_id, chat_id, role)
        SELECT id, telegram_chat_id, 'owner'
        FROM stores
        WHERE telegram_chat_id IS NOT NULL
          AND TRIM(telegram_chat_id) <> ''
        ON CONFLICT (store_id, chat_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    # Drop order: indexes → table. Backfill is not reversed — the
    # legacy `stores.telegram_chat_id` column still holds the original
    # value, so downgrade loses only the per-subscriber rows added
    # post-migration (expected trade-off for any many-to-one rollback).
    op.execute("DROP INDEX IF EXISTS ix_store_telegram_subscribers_chat;")
    op.execute("DROP INDEX IF EXISTS ix_store_telegram_subscribers_store;")
    op.execute("DROP TABLE IF EXISTS store_telegram_subscribers CASCADE;")

"""Add push_tokens table (T5-07).

One row per (user, device). Used by the FCM sender to know where to
fan out ORANGE/RED alerts. Users can register the same token more
than once safely — UNIQUE on the raw token enforces idempotency.

Revision ID: 20260424_05
Revises: 20260424_04
"""

from alembic import op

revision = "20260424_05"
down_revision = "20260424_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
        """
        CREATE INDEX IF NOT EXISTS ix_push_tokens_user
            ON push_tokens (user_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_push_tokens_user;")
    op.execute("DROP TABLE IF EXISTS push_tokens CASCADE;")

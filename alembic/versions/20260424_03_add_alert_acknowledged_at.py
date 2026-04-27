"""Add alerts.acknowledged_at + acknowledged_by_chat_id (T5-05).

Inline Telegram ack button needs a durable "this alert is handled"
marker. Two columns land together:

* `acknowledged_at TIMESTAMPTZ NULL` — NULL = unacknowledged. The
  common dashboard query filters on `IS NULL`, so a partial index
  narrows the hot path to rows that actually matter.
* `acknowledged_by_chat_id TEXT NULL` — which Telegram chat_id hit
  the inline button. Kept deliberately loose (TEXT, no FK) because
  the subscriber row may get cleaned up later but the audit trail
  must survive.

Revision ID: 20260424_03
Revises: 20260424_02
"""

from alembic import op

revision = "20260424_03"
down_revision = "20260424_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE alerts
        ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ;
        """
    )
    op.execute(
        """
        ALTER TABLE alerts
        ADD COLUMN IF NOT EXISTS acknowledged_by_chat_id TEXT;
        """
    )
    # Partial index — most dashboards show "unacknowledged alerts"
    # sorted by time. Index only those rows so adding the column is
    # cheap on large alert tables.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_alerts_unacknowledged_event_time
        ON alerts (event_time DESC)
        WHERE acknowledged_at IS NULL;
        """
    )


def downgrade() -> None:
    # Drop order: index → columns. IF EXISTS everywhere so a partial
    # upgrade → downgrade converges without manual DBA cleanup.
    op.execute("DROP INDEX IF EXISTS ix_alerts_unacknowledged_event_time;")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS acknowledged_by_chat_id;")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS acknowledged_at;")

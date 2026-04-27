"""Add alert_escalations table (T5-09).

One row per delivery attempt, per channel. Rows are additive: a single
alert can produce telegram + email + fcm + sms escalations in the same
second and we want to see all four in the customer portal. The
`delivered_at`/`failed_at`/`error` triad captures the outcome so the
dashboard can distinguish "sent successfully" from "provider refused"
without re-parsing logs.

The table deliberately does NOT enforce `FOREIGN KEY(alert_id)` with
`ON DELETE CASCADE` — T2-23's retention sweeper deletes alerts older
than 30 days, and we want the escalation audit trail to outlive the
alert row for compliance. A soft FK via explicit `alert_id` join keeps
the behaviour explicit.

Revision ID: 20260424_04
Revises: 20260424_03
"""

from alembic import op

revision = "20260424_04"
down_revision = "20260424_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
        """
        CREATE INDEX IF NOT EXISTS ix_alert_escalations_alert
            ON alert_escalations (alert_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_alert_escalations_channel_recent
            ON alert_escalations (channel, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_alert_escalations_channel_recent;")
    op.execute("DROP INDEX IF EXISTS ix_alert_escalations_alert;")
    op.execute("DROP TABLE IF EXISTS alert_escalations CASCADE;")

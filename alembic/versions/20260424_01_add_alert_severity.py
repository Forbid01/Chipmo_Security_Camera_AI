"""Add alerts.severity column (T5-02).

4-level classifier (GREEN / YELLOW / ORANGE / RED) needs a column so
the review dashboard + BI queries can filter by tier without
recomputing from `confidence_score`. Backfill reads existing
confidence_score values through the same 40/70/85 thresholds used by
the live classifier (`app.core.severity`) so historical rows line up
with new ones.

Revision ID: 20260424_01
Revises: 20260423_02
"""

from alembic import op

revision = "20260424_01"
down_revision = "20260423_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the column NOT NULL with a default so existing rows get
    # 'green' for free. The backfill below overrides that with tier
    # values derived from confidence_score where available.
    op.execute(
        """
        ALTER TABLE alerts
        ADD COLUMN IF NOT EXISTS severity VARCHAR(16) NOT NULL DEFAULT 'green';
        """
    )
    op.execute(
        """
        ALTER TABLE alerts
        ADD CONSTRAINT alerts_severity_valid
        CHECK (severity IN ('green', 'yellow', 'orange', 'red'));
        """
    )

    # Backfill — T5-01 thresholds (40 / 70 / 85) applied to any
    # existing `confidence_score`. Rows missing a score stay 'green'
    # from the column default.
    op.execute(
        """
        UPDATE alerts
        SET severity = CASE
            WHEN confidence_score IS NULL THEN 'green'
            WHEN confidence_score >= 85 THEN 'red'
            WHEN confidence_score >= 70 THEN 'orange'
            WHEN confidence_score >= 40 THEN 'yellow'
            ELSE 'green'
        END
        WHERE severity = 'green';
        """
    )

    # Partial index — most dashboard queries filter to the non-green
    # tier (green is "why was this alert even raised?" and is rare
    # post-T5-01 anyway). Indexing only the triaged tiers keeps the
    # index small while still speeding up the hot path.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_alerts_severity_nongreen
        ON alerts (severity)
        WHERE severity <> 'green';
        """
    )


def downgrade() -> None:
    # Drop order: index → check constraint → column. Every statement
    # uses IF EXISTS so a partial upgrade → downgrade converges.
    op.execute("DROP INDEX IF EXISTS ix_alerts_severity_nongreen;")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_severity_valid;")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS severity;")

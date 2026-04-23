"""add store_fp_rate_daily materialized view

Revision ID: 20260421_09
Revises: 20260421_08
Create Date: 2026-04-21 00:00:00

Per the T02-07 spike (docs/spikes/timescaledb-integration.md §4.1 rule 4):
this ships as a plain Postgres materialized view + scheduled refresh
job. When TimescaleDB lands on self-hosted central, the view is a
drop-in replacement for a continuous aggregate — the underlying SELECT
stays identical.

Key details:
- `date_trunc('day', event_time)` in place of Timescale-only
  `time_bucket` so the view runs on vanilla Postgres today.
- Unique index on `(store_id, day)` so
  `REFRESH MATERIALIZED VIEW CONCURRENTLY` is legal. Without the unique
  index, CONCURRENTLY is rejected and the refresh blocks readers.
- Only counts rows with a non-null `store_id`; legacy pre-migration
  rows sometimes carry NULL store_id and their counts are not
  attributable.
- Counts the RAG/VLM pipeline columns too: suppressed alerts don't
  count toward FP/TP (they were never shown to the user). This uses
  `suppressed` from T02-14 if available; falls back cleanly when the
  column is missing.
"""

from alembic import op

revision = "20260421_09"
down_revision = "20260421_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The view references `suppressed` from T02-14. Guard the SQL so a
    # staging box that ran this migration before running T02-07 still
    # works — `suppressed` is the only newly-added column we reference,
    # so we branch the DDL on its presence.
    op.execute("""
        DO $$
        DECLARE
            has_suppressed BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'alerts'
                  AND column_name = 'suppressed'
            ) INTO has_suppressed;

            IF has_suppressed THEN
                EXECUTE $view$
                    CREATE MATERIALIZED VIEW IF NOT EXISTS store_fp_rate_daily AS
                    SELECT
                        store_id,
                        date_trunc('day', event_time) AS day,
                        COUNT(*) FILTER (
                            WHERE feedback_status = 'false_positive'
                              AND COALESCE(suppressed, FALSE) = FALSE
                        ) AS false_positives,
                        COUNT(*) FILTER (
                            WHERE feedback_status = 'true_positive'
                              AND COALESCE(suppressed, FALSE) = FALSE
                        ) AS true_positives,
                        COUNT(*) FILTER (
                            WHERE COALESCE(suppressed, FALSE) = FALSE
                        ) AS total_alerts,
                        COUNT(*) FILTER (
                            WHERE COALESCE(suppressed, FALSE) = TRUE
                        ) AS suppressed_alerts
                    FROM alerts
                    WHERE store_id IS NOT NULL
                    GROUP BY store_id, date_trunc('day', event_time)
                    WITH NO DATA
                $view$;
            ELSE
                EXECUTE $view$
                    CREATE MATERIALIZED VIEW IF NOT EXISTS store_fp_rate_daily AS
                    SELECT
                        store_id,
                        date_trunc('day', event_time) AS day,
                        COUNT(*) FILTER (
                            WHERE feedback_status = 'false_positive'
                        ) AS false_positives,
                        COUNT(*) FILTER (
                            WHERE feedback_status = 'true_positive'
                        ) AS true_positives,
                        COUNT(*) AS total_alerts,
                        0::bigint AS suppressed_alerts
                    FROM alerts
                    WHERE store_id IS NOT NULL
                    GROUP BY store_id, date_trunc('day', event_time)
                    WITH NO DATA
                $view$;
            END IF;
        END $$;

        -- Unique index is required for REFRESH ... CONCURRENTLY.
        CREATE UNIQUE INDEX IF NOT EXISTS uq_store_fp_rate_daily_store_day
            ON store_fp_rate_daily (store_id, day);

        -- Speeds up the common "last 30 days for store X" query.
        CREATE INDEX IF NOT EXISTS idx_store_fp_rate_daily_day
            ON store_fp_rate_daily (day DESC);

        -- Seed the view with current data. Uses a non-concurrent refresh
        -- because the view is empty (WITH NO DATA) at this point.
        REFRESH MATERIALIZED VIEW store_fp_rate_daily;
    """)


def downgrade() -> None:
    op.execute("""
        DROP MATERIALIZED VIEW IF EXISTS store_fp_rate_daily;
    """)

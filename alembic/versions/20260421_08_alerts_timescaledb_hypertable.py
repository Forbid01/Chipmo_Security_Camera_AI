"""convert alerts to TimescaleDB hypertable with 2-year retention

Revision ID: 20260421_08
Revises: 20260421_07
Create Date: 2026-04-21 00:00:00

Owned by T02-15. Per the T02-07 spike
(docs/spikes/timescaledb-integration.md) TimescaleDB is deferred until
the self-hosted central phase. Running this migration against Railway's
managed Postgres is a **no-op**: the extension isn't available, so the
`DO $$ BEGIN … END $$` block short-circuits.

Activation rules:
1. `pg_available_extensions` must list `timescaledb`.
2. `TIMESCALEDB_ENABLED=1` must be set in the migration environment.

Both checks happen at migration time so a stale env flag on a
managed-Postgres host cannot crash `alembic upgrade head`.

Retention policy: 2 years across the whole table. Labeled-alert
preservation beyond 2 years is handled out-of-band (clip storage +
`alert_feedback` row keep their own retention — see
docs/09-PRIVACY-LEGAL.md §3.6).

Downgrade removes the retention policy and is a no-op when the
extension was never enabled. A hypertable cannot be cleanly demoted to
a plain table, so downgrade leaves the shape as-is; data is preserved
and subsequent `alembic upgrade` can re-attach the policy.
"""

import os

from alembic import op

revision = "20260421_08"
down_revision = "20260421_07"
branch_labels = None
depends_on = None


def _timescaledb_requested() -> bool:
    raw = os.environ.get("TIMESCALEDB_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def upgrade() -> None:
    if not _timescaledb_requested():
        # Deferred per the T02-07 decision. Leave alerts as a plain
        # Postgres table. The downstream migration chain remains valid.
        return

    op.execute("""
        DO $$
        DECLARE
            ts_installed BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
            ) INTO ts_installed;

            IF NOT ts_installed THEN
                RAISE NOTICE
                    'TimescaleDB not installed; alerts hypertable '
                    'conversion skipped. See '
                    'docs/spikes/timescaledb-integration.md.';
                RETURN;
            END IF;

            PERFORM create_hypertable(
                'alerts', 'event_time',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );

            PERFORM add_retention_policy(
                'alerts', INTERVAL '2 years',
                if_not_exists => TRUE
            );
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        DECLARE
            ts_installed BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
            ) INTO ts_installed;

            IF NOT ts_installed THEN
                RETURN;
            END IF;

            PERFORM remove_retention_policy('alerts', if_exists => TRUE);
        END $$;
    """)

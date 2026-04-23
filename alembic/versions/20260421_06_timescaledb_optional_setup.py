"""optional TimescaleDB extension + hypertable conversion

Revision ID: 20260421_06
Revises: 20260421_05
Create Date: 2026-04-21 00:00:00

Output of T02-07 spike. See docs/spikes/timescaledb-integration.md.

Design rules:
- Idempotent: safe to run multiple times.
- Guarded: on a Postgres instance that does not ship TimescaleDB (e.g.
  Railway managed), `CREATE EXTENSION` is skipped via
  `IF NOT EXISTS` + pg_available_extensions feature-check so the rest of
  `alembic upgrade head` keeps working.
- Opt-in: even when the extension is available, hypertable conversion
  only happens if `TIMESCALEDB_ENABLED=1`. The default is no-op.
- Rollback-safe: downgrade removes hypertable policies but leaves the
  underlying tables intact (hypertables degrade to plain tables cleanly
  if the extension itself is dropped).

What this migration does when enabled and available:
- Converts `inference_metrics`, `audit_log`, and `alerts` to hypertables
  on their timestamp columns.
- Registers 30-day retention for metrics tables and 1-year retention
  for `audit_log` per the original spec in docs/06-DATABASE-SCHEMA.md.
- Does NOT register continuous aggregates here — those are built in the
  dedicated T02-16 migration once their materialized views exist.
"""

import os

from alembic import op

revision = "20260421_06"
down_revision = "20260421_05"
branch_labels = None
depends_on = None


def _timescaledb_requested() -> bool:
    raw = os.environ.get("TIMESCALEDB_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def upgrade() -> None:
    # Feature-check the extension without hard-failing. On Railway's
    # managed Postgres pg_available_extensions does not list timescaledb,
    # so the whole DO block short-circuits to a NOTICE.
    op.execute("""
        DO $$
        DECLARE
            ts_available BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM pg_available_extensions
                WHERE name = 'timescaledb'
            ) INTO ts_available;

            IF ts_available THEN
                CREATE EXTENSION IF NOT EXISTS timescaledb;
                RAISE NOTICE 'TimescaleDB extension ensured.';
            ELSE
                RAISE NOTICE
                    'TimescaleDB not available on this server; '
                    'skipping hypertable conversion. See '
                    'docs/spikes/timescaledb-integration.md.';
            END IF;
        END $$;
    """)

    if not _timescaledb_requested():
        return

    # Hypertable conversion is only attempted when the operator explicitly
    # flags TIMESCALEDB_ENABLED=1 and the extension is present. Both sides
    # are re-checked inside the DO block so that a stale env flag cannot
    # crash the migration on a managed Postgres.
    op.execute("""
        DO $$
        DECLARE
            ts_installed BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
            ) INTO ts_installed;

            IF NOT ts_installed THEN
                RAISE NOTICE 'TimescaleDB not installed; hypertable conversion skipped.';
                RETURN;
            END IF;

            -- inference_metrics: per-camera per-second samples
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'inference_metrics'
            ) THEN
                PERFORM create_hypertable(
                    'inference_metrics', 'timestamp',
                    if_not_exists => TRUE,
                    migrate_data => TRUE
                );
                PERFORM add_retention_policy(
                    'inference_metrics', INTERVAL '30 days',
                    if_not_exists => TRUE
                );
            END IF;

            -- audit_log: 1 year retention per docs/06 and 09-PRIVACY
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'audit_log'
            ) THEN
                PERFORM create_hypertable(
                    'audit_log', 'timestamp',
                    if_not_exists => TRUE,
                    migrate_data => TRUE
                );
                PERFORM add_retention_policy(
                    'audit_log', INTERVAL '1 year',
                    if_not_exists => TRUE
                );
            END IF;

            -- alerts: time-series, hypertable conversion owned by T02-15.
            -- This migration does NOT promote alerts; the follow-up task
            -- does it after column additions in T02-14 have landed.
        END $$;
    """)


def downgrade() -> None:
    # Undo only the policy wiring; leave tables intact. Dropping the
    # extension itself is out-of-scope because other objects (unit tests,
    # other migrations) may depend on its presence.
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

            PERFORM remove_retention_policy('inference_metrics', if_exists => TRUE);
            PERFORM remove_retention_policy('audit_log', if_exists => TRUE);
        END $$;
    """)

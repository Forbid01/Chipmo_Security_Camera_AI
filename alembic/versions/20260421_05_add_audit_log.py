"""add audit_log table

Revision ID: 20260421_05
Revises: 20260421_04
Create Date: 2026-04-21 00:00:00

Per docs/07-SCHEMA-MIGRATION-LOCK.md §7.5 (overrides 06-DB-SCHEMA §2.7):
- `id BIGSERIAL PRIMARY KEY`
- `user_id INTEGER REFERENCES users(id)`
- Polymorphic resource reference: `resource_type` + `resource_int_id` +
  `resource_uuid` + `resource_key`. Do NOT use UUID-only `resource_id`
  because current core tables (alerts, stores, cameras, users) use
  integer PKs.

Normal PostgreSQL table first; TimescaleDB hypertable + 1-year retention
is gated by T02-07. Rollback-safe, additive.
"""

from alembic import op

revision = "20260421_05"
down_revision = "20260421_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

            action VARCHAR(64) NOT NULL,

            resource_type VARCHAR(32),
            resource_int_id BIGINT,
            resource_uuid UUID,
            resource_key TEXT,

            details JSONB NOT NULL DEFAULT '{}'::jsonb,

            ip_address INET,
            user_agent TEXT,

            timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
            ON audit_log (timestamp DESC);

        CREATE INDEX IF NOT EXISTS idx_audit_log_user
            ON audit_log (user_id, timestamp DESC)
            WHERE user_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_audit_log_action
            ON audit_log (action, timestamp DESC);

        CREATE INDEX IF NOT EXISTS idx_audit_log_resource_type
            ON audit_log (resource_type, timestamp DESC)
            WHERE resource_type IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_audit_log_resource_int
            ON audit_log (resource_type, resource_int_id)
            WHERE resource_int_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_audit_log_resource_uuid
            ON audit_log (resource_type, resource_uuid)
            WHERE resource_uuid IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS audit_log;
    """)

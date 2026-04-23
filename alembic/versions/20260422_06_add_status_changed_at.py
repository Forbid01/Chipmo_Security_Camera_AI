"""add status_changed_at timestamp to tenants (T1-11)

Revision ID: 20260422_06
Revises: 20260422_05
Create Date: 2026-04-22 00:00:00

Tracks when a tenant entered its current status. The 90-day purge
cron (T1-11) reads this to decide which churned tenants are eligible
for data deletion.

- Nullable, defaults to NOW() at column creation so existing rows
  get a reasonable starting timestamp (the purge cron treats a NULL
  `status_changed_at` as "unknown" and skips the row rather than
  deleting something whose timer we can't prove).
- T1-10 transition service writes this column on every status flip.
"""

from alembic import op

revision = "20260422_06"
down_revision = "20260422_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ
                DEFAULT now();

        -- Partial index targeted at the purge cron's hot query:
        --   SELECT ... WHERE status = 'churned' AND status_changed_at < cutoff
        CREATE INDEX IF NOT EXISTS idx_tenants_churned_purge
            ON tenants (status_changed_at)
            WHERE status = 'churned';
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_tenants_churned_purge;
        ALTER TABLE tenants DROP COLUMN IF EXISTS status_changed_at;
    """)

"""add previous_api_key_hash + expires_at for 24h rotation overlap (T1-06)

Revision ID: 20260422_05
Revises: 20260422_04
Create Date: 2026-04-22 00:00:00

Key rotation handshake per DOC-05 §2.2:
1. Generate a new `sk_live_*` token, hash it with SHA-256.
2. Move the current `api_key_hash` → `previous_api_key_hash`, set
   `previous_api_key_expires_at = now() + 24h`.
3. Write the new hash to `api_key_hash`.
4. Return the raw token to the operator exactly once.

Both hashes are checked on every authenticated request until the
previous key's TTL elapses. Then the previous hash is cleared. This
lets a fleet of deployed agents roll over without downtime.

Columns are additive + nullable. Rollback is safe — legacy auth is
unaffected because both columns default NULL.
"""

from alembic import op

revision = "20260422_05"
down_revision = "20260422_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS previous_api_key_hash VARCHAR(64);

        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS previous_api_key_expires_at TIMESTAMPTZ;

        -- UNIQUE on the history column too: a rotated-out key must never
        -- collide with another tenant's active or rotated-out key. The
        -- constraint is deferred via a partial unique index because
        -- NULLs are allowed.
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_previous_api_key_hash
            ON tenants (previous_api_key_hash)
            WHERE previous_api_key_hash IS NOT NULL;

        -- Expired-rotation sweeper cron uses this index to find rows
        -- whose previous_api_key_hash should be nulled out.
        CREATE INDEX IF NOT EXISTS idx_tenants_previous_api_key_expires_at
            ON tenants (previous_api_key_expires_at)
            WHERE previous_api_key_expires_at IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_tenants_previous_api_key_expires_at;
        DROP INDEX IF EXISTS uq_tenants_previous_api_key_hash;
        ALTER TABLE tenants DROP COLUMN IF EXISTS previous_api_key_expires_at;
        ALTER TABLE tenants DROP COLUMN IF EXISTS previous_api_key_hash;
    """)

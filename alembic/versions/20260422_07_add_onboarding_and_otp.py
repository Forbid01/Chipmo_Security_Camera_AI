"""add onboarding_step + verification timestamps + otp_challenges (T2-01..T2-04)

Revision ID: 20260422_07
Revises: 20260422_06
Create Date: 2026-04-22 00:00:00

Adds the signup / verification state orthogonal to the lifecycle
`status` column (which stays at `pending` until billing flips it to
`active`):

- `tenants.onboarding_step` — sub-state for the /signup → /verify
  → /plan → /pay wizard: `pending_email`, `pending_plan`,
  `pending_payment`, `completed`.
- `tenants.email_verified_at` / `phone_verified_at` — set when the
  user submits the right OTP code for each channel.

Plus a new `otp_challenges` table that stores hashed OTP codes with
attempt counters, 15-min expiry, and multi-channel support so T2-03
can add SMS without another migration.
"""

from alembic import op

revision = "20260422_07"
down_revision = "20260422_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS onboarding_step VARCHAR(32)
                NOT NULL DEFAULT 'pending_email';

        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ;

        ALTER TABLE tenants
            ADD CONSTRAINT ck_tenants_onboarding_step
                CHECK (onboarding_step IN (
                    'pending_email', 'pending_plan',
                    'pending_payment', 'completed'
                ));

        CREATE INDEX IF NOT EXISTS idx_tenants_onboarding_step
            ON tenants (onboarding_step)
            WHERE onboarding_step <> 'completed';

        CREATE TABLE IF NOT EXISTS otp_challenges (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL
                REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            channel         VARCHAR(16) NOT NULL,
            destination     TEXT NOT NULL,
            code_hash       VARCHAR(64) NOT NULL,
            expires_at      TIMESTAMPTZ NOT NULL,
            max_attempts    INTEGER NOT NULL DEFAULT 3,
            attempts        INTEGER NOT NULL DEFAULT 0,
            used_at         TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT ck_otp_challenges_channel
                CHECK (channel IN ('email', 'sms')),
            CONSTRAINT ck_otp_challenges_attempts
                CHECK (attempts >= 0 AND attempts <= max_attempts)
        );

        CREATE INDEX IF NOT EXISTS idx_otp_challenges_tenant
            ON otp_challenges (tenant_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_otp_challenges_unused
            ON otp_challenges (tenant_id, channel, expires_at)
            WHERE used_at IS NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS otp_challenges;

        DROP INDEX IF EXISTS idx_tenants_onboarding_step;
        ALTER TABLE tenants
            DROP CONSTRAINT IF EXISTS ck_tenants_onboarding_step;
        ALTER TABLE tenants DROP COLUMN IF EXISTS phone_verified_at;
        ALTER TABLE tenants DROP COLUMN IF EXISTS email_verified_at;
        ALTER TABLE tenants DROP COLUMN IF EXISTS onboarding_step;
    """)

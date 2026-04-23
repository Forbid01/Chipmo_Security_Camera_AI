"""add tenants table (Sentry multi-tenancy foundation)

Revision ID: 20260422_01
Revises: 20260421_09
Create Date: 2026-04-22 00:00:00

Per Sentry DOC-05 §2.1 — introduces the canonical UUID-keyed `tenants`
table that owns the plan/status/quota/API-key identity for each paying
customer. All future tenant-scoped tables will FK `tenant_id` here.

Design notes:
- `tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid()` — no integer
  surrogate; the UUID is the stable external identifier.
- `email` is UNIQUE + NOT NULL so signup is idempotent on email collision.
- `api_key_hash` is SHA-256 hex of the raw `sk_live_*` key — the raw
  token is never persisted. Column is NOT NULL because a tenant row is
  only written once the signup flow has generated a key (even for trial
  tenants the key exists, it's just inactive until status='active').
- `status` constrained to the lifecycle states enumerated in the
  roadmap: pending, active, suspended, grace, churned.
- `plan` constrained to trial, starter, pro, enterprise.
- `resource_quota` is JSONB so we can add new quota dimensions
  (max_webhooks, max_api_calls, etc.) without a schema migration each
  time. A zero-arg `{}` default is intentionally disallowed — quota
  must be explicit to avoid accidentally unlimited tenants.

Rollback-safe: downgrade drops the table. No other table FKs here yet,
so drop is side-effect free on a fresh stack. On a deployment where
`tenant_id` FKs have already landed (future migration), the drop would
fail — that is the intended protection.
"""

from alembic import op

revision = "20260422_01"
down_revision = "20260421_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            legal_name          TEXT NOT NULL,
            display_name        TEXT NOT NULL,

            email               TEXT NOT NULL,
            phone               TEXT,

            status              TEXT NOT NULL DEFAULT 'pending',
            plan                TEXT NOT NULL DEFAULT 'trial',

            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            trial_ends_at       TIMESTAMPTZ,
            current_period_end  TIMESTAMPTZ,

            payment_method_id   TEXT,
            api_key_hash        TEXT NOT NULL,

            resource_quota      JSONB NOT NULL,

            CONSTRAINT uq_tenants_email UNIQUE (email),
            CONSTRAINT uq_tenants_api_key_hash UNIQUE (api_key_hash),

            CONSTRAINT ck_tenants_status CHECK (
                status IN ('pending', 'active', 'suspended', 'grace', 'churned')
            ),
            CONSTRAINT ck_tenants_plan CHECK (
                plan IN ('trial', 'starter', 'pro', 'enterprise')
            )
        );

        -- Lookups: by email during signup, by api_key_hash on every
        -- authenticated request, by status for lifecycle cron jobs.
        CREATE INDEX IF NOT EXISTS idx_tenants_status
            ON tenants (status)
            WHERE status <> 'churned';

        CREATE INDEX IF NOT EXISTS idx_tenants_trial_ends_at
            ON tenants (trial_ends_at)
            WHERE trial_ends_at IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_tenants_current_period_end
            ON tenants (current_period_end)
            WHERE current_period_end IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS tenants;
    """)

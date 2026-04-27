"""Add agents table (T4-07).

Edge agents register themselves on first start and heartbeat every
minute after that. The table is tenant-scoped (RLS applies) and
UNIQUE on (tenant_id, hostname) so a restarted agent is idempotent
without an operator-visible agent_id change.

Revision ID: 20260423_02
Revises: 20260423_01
"""

from alembic import op

revision = "20260423_02"
down_revision = "20260423_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            agent_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            hostname          TEXT NOT NULL,
            platform          TEXT NOT NULL,
            agent_version     TEXT,
            registered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_heartbeat_at TIMESTAMPTZ,
            metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,

            CONSTRAINT agents_platform_valid CHECK (platform IN ('linux', 'windows', 'macos')),
            CONSTRAINT agents_tenant_hostname_unique UNIQUE (tenant_id, hostname)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agents_tenant
            ON agents (tenant_id);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agents_last_heartbeat
            ON agents (last_heartbeat_at DESC NULLS LAST)
            WHERE last_heartbeat_at IS NOT NULL;
        """
    )

    # Row-level security — same pattern as every other tenant-scoped
    # table (T1-04). `bypass_tenant=on` escapes RLS for the super-admin
    # paths; otherwise tenant_id must match the session GUC.
    op.execute("ALTER TABLE agents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE agents FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON agents
            USING (
                current_setting('app.bypass_tenant', TRUE) = 'on'
                OR tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
            )
            WITH CHECK (
                current_setting('app.bypass_tenant', TRUE) = 'on'
                OR tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
            );
        """
    )


def downgrade() -> None:
    # Drop order: indexes → policy/RLS (implicit via DROP TABLE) → table.
    # All statements use IF EXISTS so a partial upgrade followed by
    # downgrade doesn't fail on a missing object — the caller can
    # rerun `alembic downgrade` to converge on a clean state.
    #
    # Atomicity note: Alembic wraps the whole downgrade in a single
    # transaction on PostgreSQL (the default), so either every statement
    # below succeeds or none do. If the migration fails mid-way on a
    # database that was MANUALLY modified outside Alembic, operators
    # should run the three statements below by hand — they are safe to
    # re-issue repeatedly.
    op.execute("DROP INDEX IF EXISTS idx_agents_last_heartbeat;")
    op.execute("DROP INDEX IF EXISTS idx_agents_tenant;")
    op.execute("DROP TABLE IF EXISTS agents CASCADE;")

"""add organization_tenant_map + dual-write view (T1-02)

Revision ID: 20260422_02
Revises: 20260422_01
Create Date: 2026-04-22 00:00:00

Bridges the integer-keyed `organizations` schema to the UUID-keyed
`tenants` schema introduced in T1-01. Enables gradual migration:

- `organization_tenant_map(organization_id, tenant_id)` gives every
  existing organization a UUID tenant.
- View `organization_tenants` joins organization + tenant so legacy
  code that filters by organization_id can also fetch the new
  tenant_id without query rewrites.
- Backfill DO block creates one stub tenant per existing org. Stub
  email is `org-{id}@migration.chipmo.mn` and API key hash is a
  throwaway placeholder — both must be rotated through the normal
  /signup + /api-key endpoints before the tenant goes live.

Rollback drops the view + map. Backfilled tenant rows are kept so
downgrade doesn't orphan data that's later FK'd by tenant_id columns.
"""

from alembic import op

revision = "20260422_02"
down_revision = "20260422_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE TABLE IF NOT EXISTS organization_tenant_map (
            organization_id INTEGER PRIMARY KEY
                REFERENCES organizations(id) ON DELETE CASCADE,
            tenant_id       UUID NOT NULL UNIQUE
                REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_organization_tenant_map_tenant
            ON organization_tenant_map (tenant_id);

        CREATE OR REPLACE VIEW organization_tenants AS
        SELECT
            o.id                  AS organization_id,
            o.name                AS organization_name,
            m.tenant_id,
            t.display_name        AS tenant_display_name,
            t.legal_name          AS tenant_legal_name,
            t.plan,
            t.status,
            t.created_at          AS tenant_created_at
        FROM organizations o
        LEFT JOIN organization_tenant_map m ON o.id = m.organization_id
        LEFT JOIN tenants t ON m.tenant_id = t.tenant_id;

        -- Backfill: one stub tenant per unmapped org. Idempotent via
        -- the LEFT JOIN / IS NULL guard.
        DO $$
        DECLARE
            org RECORD;
            new_tid UUID;
        BEGIN
            FOR org IN
                SELECT o.id, o.name
                FROM organizations o
                LEFT JOIN organization_tenant_map m
                    ON o.id = m.organization_id
                WHERE m.organization_id IS NULL
            LOOP
                INSERT INTO tenants (
                    legal_name,
                    display_name,
                    email,
                    status,
                    plan,
                    api_key_hash,
                    resource_quota
                ) VALUES (
                    COALESCE(org.name, 'Organization ' || org.id::text),
                    COALESCE(org.name, 'Organization ' || org.id::text),
                    'org-' || org.id || '@migration.chipmo.mn',
                    'active',
                    'starter',
                    encode(
                        digest(
                            'migration-org-' || org.id::text
                              || '-' || clock_timestamp()::text,
                            'sha256'
                        ),
                        'hex'
                    ),
                    jsonb_build_object(
                        'max_cameras', 5,
                        'max_stores', 1,
                        'max_gpu_seconds_per_day', 21600,
                        'max_storage_gb', 10,
                        'max_api_calls_per_minute', 30
                    )
                )
                RETURNING tenant_id INTO new_tid;

                INSERT INTO organization_tenant_map
                    (organization_id, tenant_id)
                VALUES (org.id, new_tid);
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    # Keep backfilled tenant rows around — later migrations FK into
    # them. Only drop the bridge objects.
    op.execute("""
        DROP VIEW IF EXISTS organization_tenants;
        DROP TABLE IF EXISTS organization_tenant_map;
    """)

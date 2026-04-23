"""add tenant_id UUID column + FK + index on tenant-scoped tables (T1-03)

Revision ID: 20260422_03
Revises: 20260422_02
Create Date: 2026-04-22 00:00:00

Adds `tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE CASCADE`
to every tenant-scoped table per Sentry DOC-05 §3.1:

    alerts, cameras, stores, alert_feedback, cases, sync_packs,
    inference_metrics, camera_health

Column is nullable during rollout — the T1-04 RLS migration enforces
per-row visibility, and the application layer pins tenant_id on all
new writes. A follow-up migration will promote to NOT NULL once all
legacy writers are retired.

Backfill:
- Tables with `organization_id` (alerts) map via
  `organization_tenant_map` directly.
- Tables that FK to stores (cameras, stores self, alert_feedback,
  cases, sync_packs, camera_health) derive from
  `stores.organization_id`.
- `inference_metrics` derives via cameras → stores.

Index choice: btree on a single UUID column. The task spec mentions
"GIN index", but GIN requires a multi-value / composite type (JSONB,
array, tsvector); Postgres rejects GIN on a plain UUID column unless
`btree_gin` is loaded. Btree is the standard choice for equality /
range lookups on single-value columns and matches what the RLS policy
actually needs at scan time.
"""

from alembic import op

revision = "20260422_03"
down_revision = "20260422_02"
branch_labels = None
depends_on = None


# Tables that need tenant_id + FK + index. Order: stores first so
# downstream tables can backfill via stores.tenant_id if we ever chain.
_TENANT_TABLES = (
    "stores",
    "cameras",
    "alerts",
    "alert_feedback",
    "cases",
    "sync_packs",
    "inference_metrics",
    "camera_health",
)


def upgrade() -> None:
    # 1. Add column + FK to every tenant-scoped table.
    for table in _TENANT_TABLES:
        op.execute(f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS tenant_id UUID
                    REFERENCES tenants(tenant_id) ON DELETE CASCADE;
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table}_tenant
                ON {table} (tenant_id)
                WHERE tenant_id IS NOT NULL;
        """)

    # 2. Backfill via organization_tenant_map.

    # stores has organization_id directly.
    op.execute("""
        UPDATE stores s
           SET tenant_id = m.tenant_id
          FROM organization_tenant_map m
         WHERE s.organization_id = m.organization_id
           AND s.tenant_id IS NULL;
    """)

    # cameras: prefer stores.tenant_id, fall back to cameras.organization_id
    op.execute("""
        UPDATE cameras c
           SET tenant_id = s.tenant_id
          FROM stores s
         WHERE c.store_id = s.id
           AND c.tenant_id IS NULL
           AND s.tenant_id IS NOT NULL;

        UPDATE cameras c
           SET tenant_id = m.tenant_id
          FROM organization_tenant_map m
         WHERE c.organization_id = m.organization_id
           AND c.tenant_id IS NULL;
    """)

    # alerts: organization_id directly.
    op.execute("""
        UPDATE alerts a
           SET tenant_id = m.tenant_id
          FROM organization_tenant_map m
         WHERE a.organization_id = m.organization_id
           AND a.tenant_id IS NULL;
    """)

    # alert_feedback → store_id.
    op.execute("""
        UPDATE alert_feedback f
           SET tenant_id = s.tenant_id
          FROM stores s
         WHERE f.store_id = s.id
           AND f.tenant_id IS NULL
           AND s.tenant_id IS NOT NULL;
    """)

    # cases → store_id.
    op.execute("""
        UPDATE cases c
           SET tenant_id = s.tenant_id
          FROM stores s
         WHERE c.store_id = s.id
           AND c.tenant_id IS NULL
           AND s.tenant_id IS NOT NULL;
    """)

    # sync_packs → store_id.
    op.execute("""
        UPDATE sync_packs sp
           SET tenant_id = s.tenant_id
          FROM stores s
         WHERE sp.store_id = s.id
           AND sp.tenant_id IS NULL
           AND s.tenant_id IS NOT NULL;
    """)

    # inference_metrics → camera_id → store → tenant.
    op.execute("""
        UPDATE inference_metrics im
           SET tenant_id = c.tenant_id
          FROM cameras c
         WHERE im.camera_id = c.id
           AND im.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL;
    """)

    # camera_health → camera_id → tenant (direct) or store_id.
    op.execute("""
        UPDATE camera_health ch
           SET tenant_id = c.tenant_id
          FROM cameras c
         WHERE ch.camera_id = c.id
           AND ch.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL;
    """)


def downgrade() -> None:
    # Drop in reverse so FKs unwind cleanly.
    for table in reversed(_TENANT_TABLES):
        op.execute(f"""
            DROP INDEX IF EXISTS idx_{table}_tenant;
            ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id;
        """)

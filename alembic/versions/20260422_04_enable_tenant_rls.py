"""enable per-row tenant isolation via Postgres RLS (T1-04)

Revision ID: 20260422_04
Revises: 20260422_03
Create Date: 2026-04-22 00:00:00

Second-layer defense for tenant isolation (complements the application
layer `require_*_access` dependencies). For every tenant-scoped table:

- `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` so policies
  apply to every role, including the table owner connection that
  Railway / Docker containers ship with.
- `tenant_isolation` policy: FOR ALL, permissive, checked on both
  USING (reads) and WITH CHECK (writes).

Policy logic:
    bypass_tenant = 'on'                       → all rows visible
    OR tenant_id = app.current_tenant_id::uuid → matching rows only
    OR                                         → no rows (fail-closed)

The GUCs are populated by the SQLAlchemy event hook in
`app.db.tenancy_events` (already wired for the legacy
`app.current_org_id`; the follow-up code task adds `app.current_tenant_id`).

Feature-flag:
    TENANCY_RLS_ENFORCED=1  → app sets app.current_tenant_id per request
    TENANCY_RLS_ENFORCED=0  → app sets app.bypass_tenant='on' at session
                              start, effectively disabling RLS

The migration itself always installs the policies. The flag controls
application behavior, not DDL. This lets a deploy roll out the schema
change first, then the enforcement toggle separately.

Rollback drops the policies and disables RLS on every table.
"""

from alembic import op

revision = "20260422_04"
down_revision = "20260422_03"
branch_labels = None
depends_on = None


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

_POLICY_BODY = """
    COALESCE(current_setting('app.bypass_tenant', true), 'off') = 'on'
    OR tenant_id = NULLIF(
        current_setting('app.current_tenant_id', true), ''
    )::uuid
"""


def upgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

            DROP POLICY IF EXISTS tenant_isolation ON {table};

            CREATE POLICY tenant_isolation ON {table}
                AS PERMISSIVE
                FOR ALL
                TO PUBLIC
                USING ({_POLICY_BODY})
                WITH CHECK ({_POLICY_BODY});
        """)


def downgrade() -> None:
    for table in reversed(_TENANT_TABLES):
        op.execute(f"""
            DROP POLICY IF EXISTS tenant_isolation ON {table};
            ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """)

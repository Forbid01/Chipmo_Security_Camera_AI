"""Tests for T1-04 — RLS policies + TENANCY_RLS_ENFORCED feature flag.

The migration emits policies via an f-string loop over
`_TENANT_TABLES`, so per-table substring matches on the source file
would never hit. The tests instead verify the template shape plus the
module constant that drives which tables are covered.
"""

import importlib.util
import pathlib

import pytest

from shoplift_detector.app.core.config import Settings

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260422_04_enable_tenant_rls.py"
)

TENANT_SCOPED_TABLES = (
    "stores",
    "cameras",
    "alerts",
    "alert_feedback",
    "cases",
    "sync_packs",
    "inference_metrics",
    "camera_health",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "tenant_rls_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain():
    module = _load_migration()
    assert module.revision == "20260422_04"
    assert module.down_revision == "20260422_03"


def test_migration_covers_every_tenant_scoped_table():
    module = _load_migration()
    assert set(module._TENANT_TABLES) == set(TENANT_SCOPED_TABLES)


def test_enable_and_force_row_level_security_templates():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in text
    # FORCE is required so the table-owner connection (what the app
    # and migrations use) also honors the policies.
    assert "ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in text


def test_tenant_isolation_policy_template_present():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE POLICY tenant_isolation ON {table}" in text
    # Drop-if-exists before create so re-running the migration is safe.
    assert "DROP POLICY IF EXISTS tenant_isolation ON {table}" in text


def test_policy_body_checks_both_guc_sources():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # Super-admin bypass path.
    assert "current_setting('app.bypass_tenant', true)" in text
    # Normal tenant-pin path.
    assert "current_setting('app.current_tenant_id', true)" in text
    # Fail-closed when GUC is empty string (NULLIF converts to NULL,
    # and UUID = NULL is NULL which RLS treats as reject).
    assert "NULLIF(" in text


def test_policy_enforces_both_read_and_write_paths():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "USING (" in text
    # WITH CHECK is what prevents cross-tenant INSERT / UPDATE.
    assert "WITH CHECK (" in text


def test_downgrade_template_drops_policy_and_disables_rls():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    body = text.split("def downgrade()", 1)[1]
    assert "DROP POLICY IF EXISTS tenant_isolation ON {table}" in body
    assert "ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY" in body
    assert "ALTER TABLE {table} DISABLE ROW LEVEL SECURITY" in body
    # Reverse iteration keeps FKs unwinding cleanly.
    assert "reversed(_TENANT_TABLES)" in body


def test_feature_flag_lives_on_settings_and_defaults_off():
    # Must be false by default so a migration can land before the
    # app code that pins app.current_tenant_id is ready.
    assert "TENANCY_RLS_ENFORCED" in Settings.model_fields
    default = Settings.model_fields["TENANCY_RLS_ENFORCED"].default
    assert default is False


@pytest.mark.parametrize("table", TENANT_SCOPED_TABLES)
def test_each_tenant_table_listed_in_module_constant(table):
    module = _load_migration()
    assert table in module._TENANT_TABLES

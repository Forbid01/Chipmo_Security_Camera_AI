"""Tests for T1-03 — tenant_id UUID column on all tenant-scoped tables.

The migration emits DDL via an f-string loop over `_TENANT_TABLES`, so
table-by-table string matching against the source file would never
hit. Tests instead verify:
- the module's _TENANT_TABLES tuple enumerates every DOC-05 §3.1 table
- the templated DDL fragments (ADD COLUMN, FK, partial index) appear
  once each so every table is treated identically
- the backfill SQL reaches every table via the right join path
"""

import importlib.util
import pathlib

import pytest

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260422_03_add_tenant_id_columns.py"
)

# Canonical per DOC-05 §3.1.
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
        "tenant_id_columns_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain():
    module = _load_migration()
    assert module.revision == "20260422_03"
    assert module.down_revision == "20260422_02"


def test_migration_covers_every_tenant_scoped_table():
    module = _load_migration()
    assert set(module._TENANT_TABLES) == set(TENANT_SCOPED_TABLES)


def test_add_column_ddl_template_present():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # f-string template with `{table}` placeholder. Appears once —
    # the loop reuses it for every table.
    assert "ALTER TABLE {table}" in text
    assert "ADD COLUMN IF NOT EXISTS tenant_id UUID" in text


def test_fk_cascades_on_tenant_delete():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # DOC-05 §7.3 right-to-forget: deleting a tenant must cascade.
    assert "REFERENCES tenants(tenant_id) ON DELETE CASCADE" in text


def test_partial_index_template_present():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # Partial index lets us skip pre-backfill NULL rows cheaply.
    assert "CREATE INDEX IF NOT EXISTS idx_{table}_tenant" in text
    assert "ON {table} (tenant_id)" in text
    assert "WHERE tenant_id IS NOT NULL" in text


def test_backfill_uses_organization_tenant_map_for_orgful_tables():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # stores + alerts have organization_id directly.
    assert "UPDATE stores s" in text
    assert "UPDATE alerts a" in text
    assert "organization_tenant_map m" in text


def test_backfill_walks_stores_for_indirect_tables():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # alert_feedback, cases, sync_packs all FK stores → derive through it.
    for table in ("alert_feedback", "cases", "sync_packs"):
        assert f"UPDATE {table}" in text
    assert "FROM stores s" in text


def test_backfill_walks_cameras_for_inference_metrics_and_health():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "UPDATE inference_metrics im" in text
    assert "UPDATE camera_health ch" in text
    assert "FROM cameras c" in text


def test_downgrade_templates_drop_column_and_index():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    body = text.split("def downgrade()", 1)[1]
    assert "DROP INDEX IF EXISTS idx_{table}_tenant" in body
    assert "ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id" in body
    # Reverse iteration so FKs unwind in the opposite order.
    assert "reversed(_TENANT_TABLES)" in body


@pytest.mark.parametrize("table", TENANT_SCOPED_TABLES)
def test_each_tenant_table_listed_in_module_constant(table):
    """Per-table param assertion — guards the constant itself."""
    module = _load_migration()
    assert table in module._TENANT_TABLES

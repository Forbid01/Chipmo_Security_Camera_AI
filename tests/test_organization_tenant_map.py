"""Tests for T1-02 — organization_tenant_map + dual-write view."""

import importlib.util
import pathlib

import pytest

from shoplift_detector.app.db.models.organization_tenant_map import (
    OrganizationTenantMap,
)

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260422_02_add_organization_tenant_map.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "org_tenant_map_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain_is_correct():
    module = _load_migration()
    assert module.revision == "20260422_02"
    assert module.down_revision == "20260422_01"


def test_migration_creates_map_table():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS organization_tenant_map" in text
    assert "organization_id INTEGER PRIMARY KEY" in text
    assert "tenant_id       UUID NOT NULL UNIQUE" in text


@pytest.mark.parametrize("fk_clause", [
    "REFERENCES organizations(id) ON DELETE CASCADE",
    "REFERENCES tenants(tenant_id) ON DELETE CASCADE",
])
def test_migration_cascades_both_foreign_keys(fk_clause):
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert fk_clause in text


def test_migration_creates_dual_write_view():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW organization_tenants" in text
    # View must surface both identifiers so legacy code can pull
    # tenant_id through org joins.
    assert "organization_id" in text
    assert "m.tenant_id" in text
    assert "LEFT JOIN organization_tenant_map" in text


def test_backfill_is_idempotent_via_is_null_guard():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # The WHERE m.organization_id IS NULL clause prevents re-creating
    # a tenant for already-mapped orgs on re-run.
    assert "WHERE m.organization_id IS NULL" in text


def test_backfill_uses_pgcrypto_sha256_for_stub_api_key():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "digest(" in text
    assert "'sha256'" in text
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in text


def test_backfill_uses_starter_plan_quotas():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # Matches DOC-05 §4.1 Starter quotas.
    assert "'max_cameras', 5" in text
    assert "'max_stores', 1" in text
    assert "'max_gpu_seconds_per_day', 21600" in text


def test_downgrade_keeps_backfilled_tenants():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    marker = "def downgrade()"
    body = text.split(marker, 1)[1]
    # The whole point of the T1-02 downgrade is that tenant rows
    # stay behind so later FK migrations don't orphan.
    assert "DROP VIEW IF EXISTS organization_tenants" in body
    assert "DROP TABLE IF EXISTS organization_tenant_map" in body
    assert "DELETE FROM tenants" not in body


def test_orm_model_primary_key_is_organization_id():
    pk = {c.name for c in OrganizationTenantMap.__table__.primary_key.columns}
    assert pk == {"organization_id"}


def test_orm_model_tenant_id_is_unique():
    col = OrganizationTenantMap.__table__.columns["tenant_id"]
    assert col.unique is True
    assert col.nullable is False

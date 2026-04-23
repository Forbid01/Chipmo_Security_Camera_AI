"""Tests for T1-01 — tenants table migration (Sentry DOC-05 §2.1).

Pins:
- migration revision chain
- every required column ships as DDL
- lifecycle + plan CHECK constraints land with the documented values
- unique constraints on email + api_key_hash
- supporting indexes for lifecycle cron lookups
- downgrade drops the table
- ORM model mirrors the DDL column set
"""

import importlib.util
import pathlib

import pytest

from shoplift_detector.app.db.models.tenant import (
    TENANT_PLANS,
    TENANT_STATUSES,
    Tenant,
)

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260422_01_add_tenants.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "tenants_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration file shape
# ---------------------------------------------------------------------------

def test_migration_revision_chain_is_correct():
    module = _load_migration_module()
    assert module.revision == "20260422_01"
    # Chains off the previous head so `alembic upgrade head` picks it up.
    assert module.down_revision == "20260421_09"


@pytest.mark.parametrize("column", [
    "tenant_id",
    "legal_name",
    "display_name",
    "email",
    "phone",
    "status",
    "plan",
    "created_at",
    "trial_ends_at",
    "current_period_end",
    "payment_method_id",
    "api_key_hash",
    "resource_quota",
])
def test_migration_creates_every_required_column(column):
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    # Each column must appear in the CREATE TABLE body.
    assert column in text_blob, f"Missing column: {column!r}"


def test_migration_uses_uuid_primary_key_with_gen_random_uuid_default():
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "tenant_id           UUID PRIMARY KEY" in text_blob
    assert "gen_random_uuid()" in text_blob


def test_migration_enforces_status_check_constraint():
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ck_tenants_status" in text_blob
    for status in ("pending", "active", "suspended", "grace", "churned"):
        assert f"'{status}'" in text_blob


def test_migration_enforces_plan_check_constraint():
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ck_tenants_plan" in text_blob
    for plan in ("trial", "starter", "pro", "enterprise"):
        assert f"'{plan}'" in text_blob


def test_migration_enforces_unique_constraints():
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "uq_tenants_email" in text_blob
    assert "uq_tenants_api_key_hash" in text_blob


def test_migration_resource_quota_is_jsonb_not_null():
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "resource_quota      JSONB NOT NULL" in text_blob


@pytest.mark.parametrize("index", [
    "idx_tenants_status",
    "idx_tenants_trial_ends_at",
    "idx_tenants_current_period_end",
])
def test_migration_creates_lifecycle_indexes(index):
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert f"CREATE INDEX IF NOT EXISTS {index}" in text_blob


def test_downgrade_drops_the_table():
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    marker = "def downgrade()"
    assert marker in text_blob
    body = text_blob.split(marker, 1)[1]
    assert "DROP TABLE IF EXISTS tenants" in body


# ---------------------------------------------------------------------------
# ORM model contract
# ---------------------------------------------------------------------------

def test_tenant_statuses_enum_matches_check_constraint():
    assert set(TENANT_STATUSES) == {
        "pending", "active", "suspended", "grace", "churned",
    }


def test_tenant_plans_enum_matches_check_constraint():
    assert set(TENANT_PLANS) == {"trial", "starter", "pro", "enterprise"}


@pytest.mark.parametrize("column_name", [
    "tenant_id",
    "legal_name",
    "display_name",
    "email",
    "phone",
    "status",
    "plan",
    "created_at",
    "trial_ends_at",
    "current_period_end",
    "payment_method_id",
    "api_key_hash",
    "resource_quota",
])
def test_orm_model_exposes_every_column(column_name):
    assert column_name in Tenant.__table__.columns, (
        f"Tenant ORM missing {column_name!r}"
    )


def test_orm_tenant_id_is_primary_key():
    pk_cols = {c.name for c in Tenant.__table__.primary_key.columns}
    assert pk_cols == {"tenant_id"}


def test_orm_email_is_unique():
    email_col = Tenant.__table__.columns["email"]
    assert email_col.unique is True
    assert email_col.nullable is False


def test_orm_api_key_hash_is_unique_and_not_null():
    col = Tenant.__table__.columns["api_key_hash"]
    assert col.unique is True
    assert col.nullable is False


def test_orm_resource_quota_is_not_null():
    col = Tenant.__table__.columns["resource_quota"]
    assert col.nullable is False


def test_orm_phone_is_nullable():
    col = Tenant.__table__.columns["phone"]
    assert col.nullable is True


def test_orm_status_and_plan_defaults():
    status_col = Tenant.__table__.columns["status"]
    plan_col = Tenant.__table__.columns["plan"]
    # Python-side defaults keep insert code terse when a tenant is
    # created without explicitly passing 'pending' / 'trial'.
    assert status_col.default.arg == "pending"
    assert plan_col.default.arg == "trial"

"""Contract tests for the cameras.shelf_zones migration.

Parse-only: the test environment doesn't have a live Postgres, so we
validate the migration file statically. Covers:
- Revision chain (chains off 20260422_07_add_onboarding_and_otp)
- Additive, idempotent upgrade (IF NOT EXISTS / DEFAULT '[]'::jsonb)
- GIN index present (JSONB zone lookups need one)
- Downgrade drops index then column
"""

import ast
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260423_01_add_camera_shelf_zones.py"
)


@pytest.fixture(scope="module")
def source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def module_ast(source: str) -> ast.Module:
    return ast.parse(source)


def _get_assign(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    return None


def test_migration_file_exists():
    assert MIGRATION.exists(), f"Missing migration at {MIGRATION}"


def test_revision_chain_is_correct(module_ast: ast.Module):
    revision = _get_assign(module_ast, "revision")
    down_revision = _get_assign(module_ast, "down_revision")
    assert isinstance(revision, ast.Constant) and revision.value == "20260423_01"
    assert isinstance(down_revision, ast.Constant)
    assert down_revision.value == "20260422_07"


def test_upgrade_adds_column_idempotently(source: str):
    # Must use IF NOT EXISTS guard so reruns (Railway restarts) are safe.
    assert "ADD COLUMN shelf_zones JSONB" in source
    assert "column_name = 'shelf_zones'" in source
    assert "IF NOT EXISTS" in source


def test_upgrade_uses_non_null_with_default(source: str):
    # NOT NULL + DEFAULT '[]' keeps the app's `list` semantics and avoids
    # NULL/empty-list branching in every SELECT path.
    assert "NOT NULL DEFAULT '[]'::jsonb" in source


def test_upgrade_creates_gin_index(source: str):
    # JSONB querying without GIN is a sequential scan — unacceptable once
    # we have 1000+ cameras per tenant.
    assert "CREATE INDEX IF NOT EXISTS ix_cameras_shelf_zones_gin" in source
    assert "USING GIN (shelf_zones)" in source


def test_downgrade_reverses_upgrade(source: str):
    # Drop index BEFORE column so the drop doesn't error on a missing index
    # reference — matches the pattern other migrations in this project use.
    idx_drop = source.index("DROP INDEX IF EXISTS ix_cameras_shelf_zones_gin")
    col_drop = source.index("ALTER TABLE cameras DROP COLUMN IF EXISTS shelf_zones")
    assert idx_drop < col_drop

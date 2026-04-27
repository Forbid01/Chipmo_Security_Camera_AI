"""Contract tests for the T5-04 store_telegram_subscribers migration.

Pins the schema + backfill so a future refactor can't silently drop
the uniqueness guarantee or the role CHECK constraint.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260424_02_add_telegram_subscribers.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "telegram_subscribers_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain():
    mod = _load_migration()
    assert mod.revision == "20260424_02"
    assert mod.down_revision == "20260424_01"


def test_creates_expected_columns():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    for token in [
        "store_telegram_subscribers",
        "store_id    INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE",
        "chat_id     TEXT NOT NULL",
        "role        TEXT NOT NULL DEFAULT 'manager'",
        "created_at  TIMESTAMPTZ NOT NULL DEFAULT now()",
    ]:
        assert token in body, f"migration missing: {token}"


def test_enforces_role_check_constraint():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "store_telegram_subscribers_role_valid" in body
    assert "CHECK (role IN ('owner', 'manager', 'staff'))" in body


def test_enforces_uniqueness():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "UNIQUE (store_id, chat_id)" in body


def test_backfills_from_legacy_singleton():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "INSERT INTO store_telegram_subscribers" in body
    assert "FROM stores" in body
    assert "telegram_chat_id IS NOT NULL" in body
    assert "ON CONFLICT (store_id, chat_id) DO NOTHING" in body
    # Backfill must assign 'owner' role so the first-subscriber semantics
    # match the legacy "store owner owns the notification channel" model.
    assert "'owner'" in body


def test_creates_lookup_indexes():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ix_store_telegram_subscribers_store" in body
    assert "ix_store_telegram_subscribers_chat" in body

"""Contract tests for T5-07 push_tokens migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260424_05_add_push_tokens.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "push_tokens_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain():
    mod = _load_migration()
    assert mod.revision == "20260424_05"
    assert mod.down_revision == "20260424_04"


def test_schema_shape():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    for token in [
        "CREATE TABLE IF NOT EXISTS push_tokens",
        "user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE",
        "token       TEXT NOT NULL UNIQUE",
        "platform    TEXT NOT NULL",
        "last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "CHECK (platform IN ('ios', 'android', 'web'))",
    ]:
        assert token in body, f"missing: {token}"


def test_user_index():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ix_push_tokens_user" in body

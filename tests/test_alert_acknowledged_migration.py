"""Contract tests for the T5-05 `alerts.acknowledged_at` migration.

Pins the schema shape + partial index + downgrade order. The column
is nullable by design (NULL = unacknowledged), which the live
dashboard queries depend on — the test asserts we never accidentally
add a NOT NULL that would break those filters.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260424_03_add_alert_acknowledged_at.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "alert_acknowledged_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain():
    mod = _load_migration()
    assert mod.revision == "20260424_03"
    assert mod.down_revision == "20260424_02"


def test_adds_nullable_acknowledged_columns():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    # NULL-able by contract — dashboards filter on IS NULL.
    assert "ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ" in body
    assert "ADD COLUMN IF NOT EXISTS acknowledged_by_chat_id TEXT" in body
    # Explicit NOT NULL on either column would break the semantics —
    # guard against accidental tightening.
    assert "acknowledged_at TIMESTAMPTZ NOT NULL" not in body


def test_adds_partial_index_for_unacknowledged():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ix_alerts_unacknowledged_event_time" in body
    assert "WHERE acknowledged_at IS NULL" in body
    assert "event_time DESC" in body


def test_downgrade_drops_in_reverse_order():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    # Index must drop before the column it depends on.
    idx = body.index("DROP INDEX IF EXISTS ix_alerts_unacknowledged_event_time")
    col = body.index("DROP COLUMN IF EXISTS acknowledged_at")
    assert idx < col
    assert "DROP COLUMN IF EXISTS acknowledged_by_chat_id" in body

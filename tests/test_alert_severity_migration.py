"""Contract tests for the T5-02 `alerts.severity` migration.

Pins the migration's load-bearing claims so a future refactor can't
silently drop the CHECK constraint or the backfill.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260424_01_add_alert_severity.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("alert_severity_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain():
    mod = _load_migration()
    assert mod.revision == "20260424_01"
    assert mod.down_revision == "20260423_02"


def test_adds_severity_column_not_null_default_green():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS severity VARCHAR(16) NOT NULL DEFAULT 'green'" in body


def test_enforces_check_constraint():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "alerts_severity_valid" in body
    assert "CHECK (severity IN ('green', 'yellow', 'orange', 'red'))" in body


def test_backfill_uses_t5_thresholds():
    """Backfill must use 40/70/85 so historical rows line up with the
    live classifier in `app.core.severity`."""
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "confidence_score >= 85 THEN 'red'" in body
    assert "confidence_score >= 70 THEN 'orange'" in body
    assert "confidence_score >= 40 THEN 'yellow'" in body
    # Null-score rows must not claim a tier they didn't earn.
    assert "WHEN confidence_score IS NULL THEN 'green'" in body


def test_adds_partial_index_for_non_green():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ix_alerts_severity_nongreen" in body
    assert "WHERE severity <> 'green'" in body


def test_downgrade_drops_column_and_constraint():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "DROP INDEX IF EXISTS ix_alerts_severity_nongreen" in body
    assert "DROP CONSTRAINT IF EXISTS alerts_severity_valid" in body
    assert "DROP COLUMN IF EXISTS severity" in body

"""Contract tests for the T5-09 `alert_escalations` migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260424_04_add_alert_escalations.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "alert_escalations_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain():
    mod = _load_migration()
    assert mod.revision == "20260424_04"
    assert mod.down_revision == "20260424_03"


def test_table_has_expected_columns():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    for token in [
        "CREATE TABLE IF NOT EXISTS alert_escalations",
        "alert_id         INTEGER NOT NULL",
        "channel          TEXT NOT NULL",
        "recipient        TEXT",
        "delivered_at     TIMESTAMPTZ",
        "failed_at        TIMESTAMPTZ",
        "error            TEXT",
        "acknowledged_by  TEXT",
    ]:
        assert token in body, f"migration missing: {token}"


def test_channel_check_constraint():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "alert_escalations_channel_valid" in body
    assert "CHECK (channel IN ('telegram', 'email', 'fcm', 'sms'))" in body


def test_outcome_coherency_constraint():
    """A row cannot be both delivered AND failed. The CHECK enforces
    exclusivity so dashboards can trust either timestamp."""
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "alert_escalations_outcome_coherent" in body
    assert "delivered_at IS NOT NULL AND failed_at IS NULL" in body


def test_no_foreign_key_to_alerts():
    """Soft FK — the retention sweeper deletes alerts older than 30d
    but we want the escalation audit trail to outlive them."""
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "REFERENCES alerts" not in body


def test_lookup_indexes_present():
    body = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ix_alert_escalations_alert" in body
    assert "ix_alert_escalations_channel_recent" in body

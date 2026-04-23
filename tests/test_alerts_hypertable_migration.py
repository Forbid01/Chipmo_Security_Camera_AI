"""Tests for T02-15 — alerts TimescaleDB hypertable + retention.

Per the T02-07 spike, this migration is gated and Railway-safe. The
tests pin:
- revision chain
- env-flag gate behavior
- presence of the guarding phrases that turn the whole upgrade into a
  no-op on unsupported deployments
- retention interval is exactly 2 years (matches docs/06-DB-SCHEMA §7)
- downgrade only touches the retention policy, never drops data
"""

import importlib.util
import os
import pathlib

import pytest

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260421_08_alerts_timescaledb_hypertable.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "alerts_hypertable_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain_follows_t02_14():
    module = _load_migration()
    assert module.revision == "20260421_08"
    assert module.down_revision == "20260421_07"


def test_migration_is_no_op_when_flag_disabled(monkeypatch):
    module = _load_migration()
    monkeypatch.delenv("TIMESCALEDB_ENABLED", raising=False)
    # The function's short-circuit path should return before calling
    # op.execute. If the flag is off, requesting the helper returns
    # False — the same check the upgrade path uses.
    assert module._timescaledb_requested() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_env_flag_truthy_values_enable_migration(value):
    module = _load_migration()
    os.environ["TIMESCALEDB_ENABLED"] = value
    try:
        assert module._timescaledb_requested() is True
    finally:
        os.environ.pop("TIMESCALEDB_ENABLED", None)


@pytest.mark.parametrize("phrase", [
    "pg_extension",            # availability guard
    "create_hypertable",       # hypertable conversion call
    "add_retention_policy",    # retention wiring
    "INTERVAL '2 years'",      # matches docs/06-DB-SCHEMA §7
    "'alerts', 'event_time'",  # target column
    "migrate_data => TRUE",    # existing rows must be preserved
])
def test_upgrade_contains_required_phrase(phrase):
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert phrase in text, f"Missing required phrase: {phrase!r}"


def test_downgrade_only_removes_retention_policy():
    """A hypertable can't be cleanly demoted, so downgrade must leave
    the table shape alone and only detach the retention policy. Guard
    against someone adding a destructive `DROP TABLE` to the downgrade.
    """
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    # Extract the downgrade body.
    marker = "def downgrade()"
    assert marker in text
    downgrade_body = text.split(marker, 1)[1]
    assert "remove_retention_policy" in downgrade_body
    assert "DROP TABLE" not in downgrade_body
    assert "TRUNCATE" not in downgrade_body


def test_migration_references_spike_doc_for_context():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "timescaledb-integration.md" in text, (
        "Migration must cite the T02-07 spike so operators know why it "
        "no-ops on managed Postgres."
    )

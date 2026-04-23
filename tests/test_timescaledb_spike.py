"""Tests locking in the T02-07 spike outputs.

The spike decision itself is documented in
docs/spikes/timescaledb-integration.md; these tests pin the code
artifacts that have to stay in sync with that decision so a future
refactor can't silently flip them:

- TIMESCALEDB_ENABLED feature flag defaults to False (Railway-safe).
- The guarded migration module loads, exposes the right revision chain,
  and does not hard-require the extension at import time.
- The env-flag gate is honored.
"""

import importlib.util
import os
import pathlib

import pytest

from shoplift_detector.app.core.config import Settings

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260421_06_timescaledb_optional_setup.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "timescaledb_optional_setup", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_timescaledb_flag_defaults_to_disabled():
    """Production safety: the default must not try to enable Timescale."""
    settings = Settings(SECRET_KEY="test")
    assert settings.TIMESCALEDB_ENABLED is False


def test_timescaledb_flag_can_be_toggled_via_env():
    os.environ["TIMESCALEDB_ENABLED"] = "true"
    try:
        settings = Settings(SECRET_KEY="test")
        assert settings.TIMESCALEDB_ENABLED is True
    finally:
        os.environ.pop("TIMESCALEDB_ENABLED", None)


def test_migration_exposes_expected_revision_chain():
    module = _load_migration_module()
    assert module.revision == "20260421_06"
    assert module.down_revision == "20260421_05"
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_migration_env_gate_reads_truthy_values():
    module = _load_migration_module()
    for value in ("1", "true", "YES", "on"):
        os.environ["TIMESCALEDB_ENABLED"] = value
        try:
            assert module._timescaledb_requested() is True
        finally:
            os.environ.pop("TIMESCALEDB_ENABLED", None)


def test_migration_env_gate_rejects_falsy_values():
    module = _load_migration_module()
    for value in ("", "0", "false", "no", "off"):
        if value:
            os.environ["TIMESCALEDB_ENABLED"] = value
        else:
            os.environ.pop("TIMESCALEDB_ENABLED", None)
        try:
            assert module._timescaledb_requested() is False
        finally:
            os.environ.pop("TIMESCALEDB_ENABLED", None)


def test_spike_document_exists_and_records_decision():
    doc = (
        pathlib.Path(__file__).resolve().parents[1]
        / "docs"
        / "spikes"
        / "timescaledb-integration.md"
    )
    assert doc.exists(), "T02-07 decision doc missing"
    content = doc.read_text(encoding="utf-8")
    # Key claims the rest of the codebase leans on
    assert "Defer TimescaleDB adoption" in content
    assert "Railway" in content
    assert "TIMESCALEDB_ENABLED" in content


@pytest.mark.parametrize("phrase", [
    "create_hypertable",
    "add_retention_policy",
    "pg_available_extensions",
])
def test_migration_upgrade_contains_expected_guards(phrase):
    """Prevent accidental removal of the extension-availability guard
    or the hypertable conversion calls during future refactors.
    """
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert phrase in text

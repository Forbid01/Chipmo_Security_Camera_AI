"""Tests for T1-14 — tenant-scope SQL linter."""

import pathlib

import pytest

from tools.tenant_query_linter import (
    BYPASS_MARKER,
    TENANT_SCOPED_TABLES,
    lint_file,
    lint_tree,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Rule unit tests — file-level lint
# ---------------------------------------------------------------------------

def test_scoped_tables_match_canonical_list():
    assert TENANT_SCOPED_TABLES == frozenset({
        "stores", "cameras", "alerts", "alert_feedback",
        "cases", "sync_packs", "inference_metrics", "camera_health",
    })


def test_query_with_tenant_id_filter_passes(tmp_path):
    sample = tmp_path / "ok.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'q = text("""\n'
        '    SELECT * FROM alerts WHERE tenant_id = :tid\n'
        '""")\n',
        encoding="utf-8",
    )
    assert lint_file(sample) == []


def test_query_with_bypass_marker_passes(tmp_path):
    sample = tmp_path / "bypass.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'q = text("""\n'
        '    -- NO_TENANT_SCOPE  cross-tenant admin roll-up\n'
        '    SELECT COUNT(*) FROM alerts\n'
        '""")\n',
        encoding="utf-8",
    )
    assert lint_file(sample) == []


def test_bare_select_on_tenant_table_flagged(tmp_path):
    sample = tmp_path / "bad.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'q = text("SELECT * FROM alerts WHERE id = :id")\n',
        encoding="utf-8",
    )
    violations = lint_file(sample)
    assert len(violations) == 1
    assert violations[0].table == "alerts"


@pytest.mark.parametrize("table", sorted(TENANT_SCOPED_TABLES))
def test_every_scoped_table_triggers_rule_when_naked(tmp_path, table):
    sample = tmp_path / f"naked_{table}.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        f'q = text("SELECT 1 FROM {table}")\n',
        encoding="utf-8",
    )
    violations = lint_file(sample)
    assert len(violations) == 1
    assert violations[0].table == table


def test_insert_without_tenant_id_flagged(tmp_path):
    sample = tmp_path / "insert.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'q = text("INSERT INTO cameras (name) VALUES (:name)")\n',
        encoding="utf-8",
    )
    violations = lint_file(sample)
    assert len(violations) == 1
    assert violations[0].table == "cameras"


def test_update_without_tenant_id_flagged(tmp_path):
    sample = tmp_path / "update.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'q = text("UPDATE stores SET name = :n WHERE id = :id")\n',
        encoding="utf-8",
    )
    violations = lint_file(sample)
    assert len(violations) == 1
    assert violations[0].table == "stores"


def test_delete_without_tenant_id_flagged(tmp_path):
    sample = tmp_path / "del.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'q = text("DELETE FROM alerts WHERE id = :id")\n',
        encoding="utf-8",
    )
    violations = lint_file(sample)
    assert len(violations) == 1
    assert violations[0].table == "alerts"


def test_non_tenant_table_ignored(tmp_path):
    """A query against `users` or `tenants` shouldn't trigger — those
    are global / admin tables."""
    sample = tmp_path / "users.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'q = text("SELECT * FROM users WHERE email = :e")\n'
        'q2 = text("SELECT * FROM tenants")\n',
        encoding="utf-8",
    )
    assert lint_file(sample) == []


def test_non_literal_text_argument_ignored(tmp_path):
    """Dynamically-built SQL is a separate audit — the linter only
    reports on literal strings it can inspect."""
    sample = tmp_path / "dyn.py"
    sample.write_text(
        'from sqlalchemy import text\n'
        'def build(sql):\n'
        '    return text(sql)\n',
        encoding="utf-8",
    )
    assert lint_file(sample) == []


def test_module_prefixed_text_call_still_inspected(tmp_path):
    """`sqlalchemy.text(...)` calls should also be walked."""
    sample = tmp_path / "mod.py"
    sample.write_text(
        'import sqlalchemy\n'
        'q = sqlalchemy.text("SELECT 1 FROM alerts")\n',
        encoding="utf-8",
    )
    violations = lint_file(sample)
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------

def test_tree_walk_skips_tests_and_tools_and_alembic(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bad.py").write_text(
        'from sqlalchemy import text\n'
        'q = text("SELECT 1 FROM alerts")\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bad.py").write_text(
        'from sqlalchemy import text\n'
        'q = text("SELECT 1 FROM alerts")\n',
        encoding="utf-8",
    )
    violations = lint_tree(tmp_path)
    paths = {v.path.name for v in violations}
    assert paths == {"bad.py"}


def test_repo_lints_clean_on_main_source_tree():
    """The project's own `shoplift_detector/app/` must pass the
    linter — if it doesn't, we've regressed tenant scoping somewhere.

    Legacy writers still filter by `organization_id` instead of
    `tenant_id` during the dual-write window (T1-02 → T1-03). Those
    queries need the explicit `-- NO_TENANT_SCOPE` marker OR a
    reference to `tenant_id`. Until the legacy handlers are cut over
    (TX-01, TX-02), we only gate new code by running the linter on
    specific hot paths.
    """
    # Smoke-test just the new tenant infra modules — they should be
    # tenant-scope-clean by construction.
    targets = [
        REPO_ROOT / "shoplift_detector" / "app" / "db" / "repository" / "tenants.py",
        REPO_ROOT / "shoplift_detector" / "app" / "services" / "tenant_lifecycle.py",
        REPO_ROOT / "shoplift_detector" / "app" / "services" / "tenant_purge.py",
        REPO_ROOT / "shoplift_detector" / "app" / "core" / "quota.py",
        REPO_ROOT / "shoplift_detector" / "app" / "core" / "tenant_auth.py",
    ]
    for path in targets:
        violations = lint_file(path)
        assert violations == [], f"regression in {path.name}: {violations!r}"


def test_bypass_marker_constant():
    # The literal lives in one place so callers can't drift to
    # `--noscope` or `# NO_TENANT_SCOPE` variants.
    assert BYPASS_MARKER == "-- NO_TENANT_SCOPE"

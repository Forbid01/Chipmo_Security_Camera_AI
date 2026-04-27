"""Migration shape tests for the rag_corpus + vlm_annotations tables.

Mirrors the audit pattern from `test_alerts_pipeline_columns.py` — load
the migration module by path and assert the structural invariants we
care about (revision chain, additive DDL, idempotent CREATE IF NOT
EXISTS, downgrade reverses everything).

We deliberately avoid running the SQL against a live DB here; the
schema is exercised end-to-end by the integration tests that spin up
the SQLite test bed.
"""

import importlib.util
import pathlib

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260427_01_add_rag_corpus_and_vlm_annotations.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "rag_corpus_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _captured_sql() -> list[str]:
    """Run upgrade()/downgrade() against a stub op and return every SQL
    string that was passed to op.execute. Lets the assertions inspect
    the DDL without an actual DB."""
    module = _load_migration_module()

    captured: list[str] = []

    class _StubOp:
        @staticmethod
        def execute(sql):
            captured.append(str(sql))

    original_op = module.op
    module.op = _StubOp
    try:
        module.upgrade()
    finally:
        module.op = original_op
    return captured


def _captured_downgrade_sql() -> list[str]:
    module = _load_migration_module()
    captured: list[str] = []

    class _StubOp:
        @staticmethod
        def execute(sql):
            captured.append(str(sql))

    original_op = module.op
    module.op = _StubOp
    try:
        module.downgrade()
    finally:
        module.op = original_op
    return captured


def test_revision_chain_is_correct():
    module = _load_migration_module()
    assert module.revision == "20260427_01"
    # Must follow the last shipped migration so a deploy applies cleanly.
    assert module.down_revision == "20260424_05"


def test_upgrade_creates_both_tables_idempotently():
    sql = " ".join(_captured_sql()).lower()
    assert "create table if not exists rag_corpus" in sql
    assert "create table if not exists vlm_annotations" in sql


def test_upgrade_uses_cascade_for_tenant_cleanup():
    sql = " ".join(_captured_sql()).lower()
    # Deleting a store must wipe its rag corpus rows; deleting an alert
    # must wipe its vlm annotation row.
    assert "references stores(id) on delete cascade" in sql
    assert "references alerts(id) on delete cascade" in sql


def test_vlm_annotation_is_one_to_one_with_alert():
    sql = " ".join(_captured_sql()).lower()
    # alert_id ... unique enforces 1:1 (one VLM annotation per alert)
    assert "alert_id    integer not null unique" in sql or "alert_id integer not null unique" in sql.replace("    ", " ")


def test_upgrade_creates_expected_indexes():
    sql = " ".join(_captured_sql()).lower()
    assert "ix_rag_corpus_store" in sql
    assert "ix_rag_corpus_doc_type" in sql
    assert "ix_vlm_annotations_alert" in sql


def test_downgrade_drops_what_upgrade_created():
    down = " ".join(_captured_downgrade_sql()).lower()
    assert "drop table if exists rag_corpus" in down
    assert "drop table if exists vlm_annotations" in down
    assert "drop index if exists ix_rag_corpus_store" in down
    assert "drop index if exists ix_vlm_annotations_alert" in down

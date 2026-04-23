"""Tests for T02-14 — alerts table edge/RAG/VLM columns.

Covers:
- migration file has the expected revision chain + additive DDL shape
- ORM model exposes the new columns + RAG_DECISIONS / VLM_DECISIONS
  constants
- AlertRepository.insert_alert survives three schema states:
  * pre-migration (new columns absent)  → skips them silently
  * post-migration with no caller data  → omits them (stays minimal)
  * post-migration with caller data     → includes them + UUID cast
- mark_suppressed() no-ops on pre-migration schema and writes on
  post-migration schema
"""

import importlib.util
import pathlib
from typing import Any

import pytest

from shoplift_detector.app.db.models.alert import RAG_DECISIONS, VLM_DECISIONS
from shoplift_detector.app.db.repository.alerts import AlertRepository

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260421_07_add_alert_pipeline_columns.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "alert_pipeline_columns_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration file shape
# ---------------------------------------------------------------------------

def test_migration_revision_chain_is_correct():
    module = _load_migration_module()
    assert module.revision == "20260421_07"
    assert module.down_revision == "20260421_06"


@pytest.mark.parametrize("column", [
    "suppressed",
    "suppressed_reason",
    "rag_decision",
    "vlm_decision",
    "person_track_id",
])
def test_migration_adds_every_required_column(column):
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert f"ADD COLUMN IF NOT EXISTS {column}" in text_blob


@pytest.mark.parametrize("index", [
    "idx_alerts_suppressed",
    "idx_alerts_person_track",
])
def test_migration_adds_every_supporting_index(index):
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert f"CREATE INDEX IF NOT EXISTS {index}" in text_blob


def test_migration_has_reversible_downgrade():
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    for column in (
        "suppressed",
        "suppressed_reason",
        "rag_decision",
        "vlm_decision",
        "person_track_id",
    ):
        assert f"DROP COLUMN IF EXISTS {column}" in text_blob


def test_suppressed_column_has_default_false():
    # Critical: existing rows must read suppressed=False without backfill.
    text_blob = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "suppressed BOOLEAN NOT NULL DEFAULT FALSE" in text_blob


# ---------------------------------------------------------------------------
# ORM model constants
# ---------------------------------------------------------------------------

def test_rag_decisions_enum_values():
    assert set(RAG_DECISIONS) == {"not_run", "passed", "suppressed_by_rag"}


def test_vlm_decisions_enum_values():
    assert set(VLM_DECISIONS) == {"not_run", "passed", "suppressed_by_vlm"}


# ---------------------------------------------------------------------------
# insert_alert — schema-drift tolerance
# ---------------------------------------------------------------------------

class _CapturingDB:
    """Minimal async DB mock capturing executed INSERT params."""

    def __init__(self, columns: set[str], returned_id: int = 1):
        self._columns = columns
        self._returned_id = returned_id
        self.insert_query: str | None = None
        self.insert_params: dict[str, Any] | None = None

    async def execute(self, query, params=None):
        query_text = str(query)
        if "FROM information_schema.columns" in query_text:
            class _R:
                def fetchall(inner_self):
                    return [(c,) for c in self._columns]
            return _R()
        if "INSERT INTO alerts" in query_text:
            self.insert_query = query_text
            self.insert_params = dict(params)

            class _R:
                def fetchone(inner_self):
                    return (self._returned_id,)
            return _R()
        if "UPDATE alerts" in query_text:
            self.insert_query = query_text
            self.insert_params = dict(params)

            class _R:
                rowcount = 1
            return _R()

        class _R:
            def fetchone(inner_self):
                return None

            def fetchall(inner_self):
                return []
        return _R()

    async def commit(self):
        pass


PRE_MIGRATION_COLUMNS = {
    "id", "person_id", "image_path", "video_path", "description",
    "organization_id", "store_id", "camera_id", "confidence_score",
    "reviewed", "feedback_status", "event_time",
}
POST_MIGRATION_COLUMNS = PRE_MIGRATION_COLUMNS | {
    "suppressed", "suppressed_reason",
    "rag_decision", "vlm_decision", "person_track_id",
}


@pytest.mark.asyncio
async def test_insert_alert_omits_pipeline_columns_on_pre_migration_schema():
    db = _CapturingDB(columns=PRE_MIGRATION_COLUMNS)
    repo = AlertRepository(db)

    new_id = await repo.insert_alert(
        person_id=1,
        image_path="/tmp/x.jpg",
        reason="test",
        store_id=5,
        camera_id=7,
        person_track_id=42,
        rag_decision="passed",
        vlm_decision="passed",
        suppressed=False,
    )

    assert new_id == 1
    assert db.insert_query is not None
    # Pipeline columns must NOT appear in the INSERT — legacy schema.
    for forbidden in (
        "person_track_id",
        "rag_decision",
        "vlm_decision",
        "suppressed",
    ):
        assert forbidden not in db.insert_query, (
            f"Pre-migration INSERT referenced {forbidden}; shoulda skipped"
        )


@pytest.mark.asyncio
async def test_insert_alert_omits_pipeline_columns_when_caller_passes_none():
    db = _CapturingDB(columns=POST_MIGRATION_COLUMNS)
    repo = AlertRepository(db)

    await repo.insert_alert(
        person_id=1,
        image_path="/tmp/x.jpg",
        reason="test",
        store_id=5,
        camera_id=7,
    )

    # Column exists in schema but caller passed nothing — still omit.
    assert "person_track_id" not in db.insert_query
    assert "rag_decision" not in db.insert_query


@pytest.mark.asyncio
async def test_insert_alert_includes_pipeline_columns_when_caller_provides_them():
    db = _CapturingDB(columns=POST_MIGRATION_COLUMNS)
    repo = AlertRepository(db)

    await repo.insert_alert(
        person_id=1,
        image_path="/tmp/x.jpg",
        reason="test",
        store_id=5,
        camera_id=7,
        person_track_id=42,
        rag_decision="passed",
        vlm_decision="passed",
        suppressed=False,
    )

    # All pipeline columns must reach the INSERT on the new schema.
    assert "person_track_id" in db.insert_query
    assert "rag_decision" in db.insert_query
    assert "vlm_decision" in db.insert_query
    # suppressed=False is a real caller signal; must be persisted
    # (repo specifically excludes only None, not False).
    assert db.insert_params["suppressed"] is False


@pytest.mark.asyncio
async def test_mark_suppressed_noop_on_pre_migration_schema():
    db = _CapturingDB(columns=PRE_MIGRATION_COLUMNS)
    repo = AlertRepository(db)

    ok = await repo.mark_suppressed(
        alert_id=99,
        reason="duplicate FP from RAG neighbor",
        rag_decision="suppressed_by_rag",
    )

    assert ok is False
    assert db.insert_query is None  # no UPDATE attempted


@pytest.mark.asyncio
async def test_mark_suppressed_writes_on_post_migration_schema():
    db = _CapturingDB(columns=POST_MIGRATION_COLUMNS)
    repo = AlertRepository(db)

    ok = await repo.mark_suppressed(
        alert_id=99,
        reason="RAG neighbor match",
        rag_decision="suppressed_by_rag",
    )

    assert ok is True
    assert "UPDATE alerts" in db.insert_query
    assert "suppressed = TRUE" in db.insert_query
    assert "rag_decision = :rag" in db.insert_query
    assert db.insert_params["reason"] == "RAG neighbor match"
    assert db.insert_params["rag"] == "suppressed_by_rag"

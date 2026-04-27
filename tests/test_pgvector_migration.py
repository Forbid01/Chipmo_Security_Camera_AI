"""Migration shape tests for the pgvector switchover.

Asserts:
- revision chain follows 20260427_01
- upgrade installs the extension idempotently
- embedding column added with correct dimension
- HNSW index created with cosine ops
- legacy qdrant_point_id column dropped
- downgrade restores qdrant_point_id but does not drop the extension
"""

import importlib.util
import pathlib

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260427_02_add_pgvector_to_rag_corpus.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "pgvector_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _captured(direction: str) -> list[str]:
    module = _load_migration_module()
    captured: list[str] = []

    class _StubOp:
        @staticmethod
        def execute(sql):
            captured.append(str(sql))

    original_op = module.op
    module.op = _StubOp
    try:
        getattr(module, direction)()
    finally:
        module.op = original_op
    return captured


def test_revision_chain():
    module = _load_migration_module()
    assert module.revision == "20260427_02"
    assert module.down_revision == "20260427_01"


def test_upgrade_installs_extension_idempotently():
    sql = " ".join(_captured("upgrade")).lower()
    assert "create extension if not exists vector" in sql


def test_upgrade_adds_embedding_column_with_dim_384():
    sql = " ".join(_captured("upgrade")).lower()
    # 384 = intfloat/multilingual-e5-small. A regression here means the
    # model and the column have drifted apart and inserts will explode.
    assert "embedding vector(384)" in sql


def test_upgrade_creates_hnsw_cosine_index():
    sql = " ".join(_captured("upgrade")).lower()
    assert "using hnsw" in sql
    assert "vector_cosine_ops" in sql


def test_upgrade_drops_legacy_qdrant_column():
    sql = " ".join(_captured("upgrade")).lower()
    assert "drop column if exists qdrant_point_id" in sql


def test_downgrade_restores_qdrant_column_but_keeps_extension():
    sql = " ".join(_captured("downgrade")).lower()
    assert "add column if not exists qdrant_point_id" in sql
    # Intentionally NOT dropping the extension — other tables may use it.
    assert "drop extension" not in sql

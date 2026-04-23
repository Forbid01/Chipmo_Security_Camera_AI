"""Tests for T1-06 — API key generator + rotation."""

import importlib.util
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

from shoplift_detector.app.db.repository.tenants import hash_api_key
from shoplift_detector.app.services.api_key_service import (
    API_KEY_PREFIX,
    ROTATION_OVERLAP,
    generate_api_key,
    rotate_api_key,
)

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260422_05_add_api_key_rotation_columns.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "api_key_rotation_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------

def test_migration_revision_chain():
    module = _load_migration()
    assert module.revision == "20260422_05"
    assert module.down_revision == "20260422_04"


def test_migration_adds_previous_key_columns():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS previous_api_key_hash VARCHAR(64)" in text
    assert "ADD COLUMN IF NOT EXISTS previous_api_key_expires_at TIMESTAMPTZ" in text


def test_migration_creates_unique_and_expires_indexes():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "uq_tenants_previous_api_key_hash" in text
    assert "idx_tenants_previous_api_key_expires_at" in text
    # Partial so NULL slots don't block rotation.
    assert "WHERE previous_api_key_hash IS NOT NULL" in text


def test_downgrade_drops_both_columns_and_indexes():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    body = text.split("def downgrade()", 1)[1]
    for token in (
        "DROP INDEX IF EXISTS idx_tenants_previous_api_key_expires_at",
        "DROP INDEX IF EXISTS uq_tenants_previous_api_key_hash",
        "DROP COLUMN IF EXISTS previous_api_key_expires_at",
        "DROP COLUMN IF EXISTS previous_api_key_hash",
    ):
        assert token in body


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def test_generate_api_key_has_expected_prefix():
    key = generate_api_key()
    assert key.raw.startswith(API_KEY_PREFIX)


def test_generate_api_key_hash_matches_raw():
    key = generate_api_key()
    assert key.hashed == hash_api_key(key.raw)
    # SHA-256 → 64 hex chars.
    assert len(key.hashed) == 64


def test_generate_api_key_is_url_safe_and_unpadded():
    key = generate_api_key()
    # urlsafe base64 — no `/`, `+`, or `=` padding in the chunk.
    chunk = key.raw[len(API_KEY_PREFIX):]
    for forbidden in ("/", "+", "="):
        assert forbidden not in chunk


def test_generate_api_key_chunk_has_minimum_entropy_length():
    key = generate_api_key()
    chunk = key.raw[len(API_KEY_PREFIX):]
    # 32 random bytes → at least 42 b64url chars after stripping pad.
    assert len(chunk) >= 42


def test_generate_api_key_is_random():
    # Trivially: two consecutive generates should not collide.
    keys = {generate_api_key().raw for _ in range(10)}
    assert len(keys) == 10


def test_rotation_overlap_is_24_hours():
    assert ROTATION_OVERLAP == timedelta(hours=24)


# ---------------------------------------------------------------------------
# Rotation service
# ---------------------------------------------------------------------------

class _FakeRepo:
    """Captures the rotation call so we can assert the contract
    without bringing up Postgres."""

    def __init__(self):
        self.rotated: dict | None = None

    async def rotate_api_key(
        self,
        *,
        tenant_id: str,
        new_hash: str,
        previous_expires_at,
        now,
    ):
        self.rotated = {
            "tenant_id": tenant_id,
            "new_hash": new_hash,
            "previous_expires_at": previous_expires_at,
            "now": now,
        }


@pytest.mark.asyncio
async def test_rotate_api_key_writes_new_hash_and_24h_expiry():
    repo = _FakeRepo()
    now = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)

    issued = await rotate_api_key(repo, tenant_id="t-1", now=now)

    assert issued.raw.startswith(API_KEY_PREFIX)
    assert repo.rotated is not None
    assert repo.rotated["new_hash"] == issued.hashed
    assert repo.rotated["previous_expires_at"] == now + ROTATION_OVERLAP
    assert repo.rotated["now"] == now


@pytest.mark.asyncio
async def test_rotate_api_key_uses_current_clock_when_no_now_passed():
    repo = _FakeRepo()
    issued = await rotate_api_key(repo, tenant_id="t-2")
    # No assertion on exact time — just that the rotation happened
    # and the expiry was set roughly 24h ahead.
    assert issued.raw.startswith(API_KEY_PREFIX)
    gap = repo.rotated["previous_expires_at"] - repo.rotated["now"]
    assert gap == ROTATION_OVERLAP

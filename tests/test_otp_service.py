"""Tests for T2-02 / T2-04 — OTP generation + verification."""

import importlib.util
import pathlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from shoplift_detector.app.services.otp_service import (
    CODE_LENGTH,
    CODE_TTL,
    MAX_ATTEMPTS,
    OtpCodeMismatch,
    OtpExhausted,
    OtpExpired,
    OtpNotFound,
    OtpRepository,
    generate_code,
    hash_code,
    issue_otp,
    verify_otp,
)

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260422_07_add_onboarding_and_otp.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "onboarding_otp_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------

def test_migration_revision_chain():
    module = _load_migration()
    assert module.revision == "20260422_07"
    assert module.down_revision == "20260422_06"


def test_migration_adds_onboarding_columns():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS onboarding_step" in text
    assert "ADD COLUMN IF NOT EXISTS email_verified_at" in text
    assert "ADD COLUMN IF NOT EXISTS phone_verified_at" in text


def test_migration_creates_otp_challenges_table():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS otp_challenges" in text
    for column in (
        "id",
        "tenant_id",
        "channel",
        "destination",
        "code_hash",
        "expires_at",
        "max_attempts",
        "attempts",
        "used_at",
    ):
        assert column in text


def test_downgrade_reverts_cleanly():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    body = text.split("def downgrade()", 1)[1]
    assert "DROP TABLE IF EXISTS otp_challenges" in body
    assert "DROP COLUMN IF EXISTS onboarding_step" in body


# ---------------------------------------------------------------------------
# Code generation + hashing
# ---------------------------------------------------------------------------

def test_generate_code_is_six_digit_numeric():
    for _ in range(50):
        code = generate_code()
        assert len(code) == CODE_LENGTH
        assert code.isdigit()


def test_hash_code_matches_sha256_hex():
    import hashlib
    assert hash_code("123456") == hashlib.sha256(b"123456").hexdigest()


def test_code_ttl_is_fifteen_minutes():
    assert CODE_TTL == timedelta(minutes=15)


def test_max_attempts_is_three():
    assert MAX_ATTEMPTS == 3


# ---------------------------------------------------------------------------
# Repository + issue / verify with an in-memory fake
# ---------------------------------------------------------------------------

class _InMemoryOtpRepo:
    """Drop-in replacement for OtpRepository that backs rows with a
    list — good enough for exercising the service-layer contract."""

    def __init__(self):
        self.rows: list[dict] = []
        self.commits = 0

    async def create(
        self, *, tenant_id, channel, destination,
        code_hash, expires_at, max_attempts=3,
    ):
        row = {
            "id": uuid4(),
            "tenant_id": tenant_id,
            "channel": channel,
            "destination": destination,
            "code_hash": code_hash,
            "expires_at": expires_at,
            "max_attempts": max_attempts,
            "attempts": 0,
            "used_at": None,
            "created_at": datetime.now(UTC),
        }
        self.rows.append(row)
        self.commits += 1
        return row

    async def get_latest_unused(self, *, tenant_id, channel):
        matches = [
            r for r in self.rows
            if r["tenant_id"] == tenant_id
            and r["channel"] == channel
            and r["used_at"] is None
        ]
        return matches[-1] if matches else None

    async def increment_attempts(self, otp_id):
        for r in self.rows:
            if r["id"] == otp_id:
                r["attempts"] += 1
                return r["attempts"]
        return 0

    async def mark_used(self, otp_id):
        for r in self.rows:
            if r["id"] == otp_id:
                r["used_at"] = datetime.now(UTC)


@pytest.mark.asyncio
async def test_issue_otp_persists_hash_and_returns_raw():
    repo = _InMemoryOtpRepo()
    tenant_id = uuid4()
    issued = await issue_otp(
        repo,
        tenant_id=tenant_id,
        channel="email",
        destination="demo@sentry.mn",
    )
    assert issued.raw_code.isdigit()
    assert len(repo.rows) == 1
    # Hash must be the SHA-256 of the raw code, not the raw itself.
    assert repo.rows[0]["code_hash"] == hash_code(issued.raw_code)
    assert repo.rows[0]["code_hash"] != issued.raw_code
    # Expiry within 15 minutes window.
    gap = repo.rows[0]["expires_at"] - datetime.now(UTC)
    assert timedelta(minutes=14) < gap <= timedelta(minutes=15, seconds=1)


@pytest.mark.asyncio
async def test_verify_success_marks_used():
    repo = _InMemoryOtpRepo()
    tid = uuid4()
    issued = await issue_otp(
        repo, tenant_id=tid, channel="email", destination="a@b",
    )
    row = await verify_otp(
        repo, tenant_id=tid, channel="email",
        submitted_code=issued.raw_code,
    )
    assert row["id"] == issued.id
    assert repo.rows[0]["used_at"] is not None


@pytest.mark.asyncio
async def test_verify_wrong_code_increments_attempts():
    repo = _InMemoryOtpRepo()
    tid = uuid4()
    await issue_otp(repo, tenant_id=tid, channel="email", destination="a@b")
    with pytest.raises(OtpCodeMismatch):
        await verify_otp(
            repo, tenant_id=tid, channel="email",
            submitted_code="000000",
        )
    assert repo.rows[0]["attempts"] == 1
    # The row is still verifiable with the real code — one mistake
    # doesn't burn the whole challenge.
    assert repo.rows[0]["used_at"] is None


@pytest.mark.asyncio
async def test_verify_exhausted_after_three_wrong_attempts():
    repo = _InMemoryOtpRepo()
    tid = uuid4()
    await issue_otp(repo, tenant_id=tid, channel="email", destination="a@b")
    for _ in range(2):
        with pytest.raises(OtpCodeMismatch):
            await verify_otp(
                repo, tenant_id=tid, channel="email",
                submitted_code="111111",
            )
    # Third wrong attempt rolls over into OtpExhausted.
    with pytest.raises(OtpExhausted):
        await verify_otp(
            repo, tenant_id=tid, channel="email",
            submitted_code="222222",
        )


@pytest.mark.asyncio
async def test_verify_expired_raises():
    repo = _InMemoryOtpRepo()
    tid = uuid4()
    issued = await issue_otp(
        repo, tenant_id=tid, channel="email", destination="a@b"
    )
    # Rewrite the row to simulate a TTL that has already passed.
    repo.rows[0]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(OtpExpired):
        await verify_otp(
            repo, tenant_id=tid, channel="email",
            submitted_code=issued.raw_code,
        )


@pytest.mark.asyncio
async def test_verify_not_found_when_no_challenge():
    repo = _InMemoryOtpRepo()
    with pytest.raises(OtpNotFound):
        await verify_otp(
            repo, tenant_id=uuid4(), channel="email",
            submitted_code="123456",
        )


@pytest.mark.asyncio
async def test_verify_picks_only_unused_rows():
    repo = _InMemoryOtpRepo()
    tid = uuid4()
    old = await issue_otp(
        repo, tenant_id=tid, channel="email", destination="a@b"
    )
    # Mark the first as used.
    await repo.mark_used(old.id)
    # A fresh challenge takes its place.
    new = await issue_otp(
        repo, tenant_id=tid, channel="email", destination="a@b"
    )
    # Submitting the old code must fail — it was already consumed.
    with pytest.raises(OtpCodeMismatch):
        await verify_otp(
            repo, tenant_id=tid, channel="email",
            submitted_code=old.raw_code,
        )
    # But the new one verifies cleanly.
    await verify_otp(
        repo, tenant_id=tid, channel="email",
        submitted_code=new.raw_code,
    )

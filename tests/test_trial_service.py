"""Tests for T2-07 — 14-day trial activation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from shoplift_detector.app.services.trial_service import (
    TRIAL_ACTIVE_QUOTA,
    TRIAL_DURATION,
    TrialAlreadyActive,
    TrialNotEligible,
    activate_trial,
)


def test_trial_duration_is_14_days():
    assert TRIAL_DURATION == timedelta(days=14)


def test_trial_quota_caps_cameras_at_five():
    assert TRIAL_ACTIVE_QUOTA["max_cameras"] == 5


def test_trial_quota_exposes_pro_level_everything_else():
    # "Full Pro features with 5-camera cap" — non-camera dimensions
    # must match Pro defaults from DOC-05 §4.1.
    assert TRIAL_ACTIVE_QUOTA["max_gpu_seconds_per_day"] == 86_400
    assert TRIAL_ACTIVE_QUOTA["max_storage_gb"] == 100
    assert TRIAL_ACTIVE_QUOTA["max_api_calls_per_minute"] == 60


class _FakeDB:
    """Minimal async DB double. Captures the UPDATE and audit INSERT
    so tests can assert the full contract without Postgres."""

    def __init__(self, tenant_row=None, update_rowcount=1):
        self._tenant_row = tenant_row
        self._update_rowcount = update_rowcount
        self.update_query: str | None = None
        self.update_params: dict | None = None
        self.audit_params: dict | None = None
        self.committed = False

    async def execute(self, query, params=None):
        q = str(query)
        if "SELECT tenant_id" in q and "FROM tenants" in q:
            return _FakeResult(row=self._tenant_row)
        if q.strip().startswith("UPDATE tenants"):
            self.update_query = q
            self.update_params = params
            return _FakeResult(rowcount=self._update_rowcount)
        if "INSERT INTO audit_log" in q:
            self.audit_params = params
            return _FakeResult(row=(1,))
        return _FakeResult()

    async def commit(self):
        self.committed = True


class _FakeResult:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or ([row] if row else [])
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


def _eligible_tenant(email="demo@sentry.mn"):
    return {
        "tenant_id": uuid4(),
        "email": email,
        "status": "pending",
        "plan": "trial",
        "onboarding_step": "pending_plan",
        "legal_name": "Номин",
        "display_name": "Номин",
        "phone": None,
        "created_at": datetime.now(UTC),
        "trial_ends_at": None,
        "current_period_end": None,
        "payment_method_id": None,
        "resource_quota": {"max_cameras": 5},
    }


@pytest.mark.asyncio
async def test_activate_trial_happy_path_returns_raw_api_key():
    db = _FakeDB(tenant_row=_eligible_tenant())
    now = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)

    result = await activate_trial(db, email="demo@sentry.mn", now=now)

    assert result.raw_api_key.startswith("sk_live_")
    assert result.trial_ends_at == now + TRIAL_DURATION
    assert result.plan == "trial"
    assert result.onboarding_step == "pending_payment"
    assert result.resource_quota["max_cameras"] == 5


@pytest.mark.asyncio
async def test_activate_trial_writes_atomic_update_with_pre_state_guard():
    db = _FakeDB(tenant_row=_eligible_tenant())
    await activate_trial(db, email="demo@sentry.mn")
    # WHERE clause must pin both status=pending and step=pending_plan
    # so a concurrent request can't slip past the guard.
    assert "status = 'pending'" in db.update_query
    assert "onboarding_step = 'pending_plan'" in db.update_query
    assert db.committed is True


@pytest.mark.asyncio
async def test_activate_trial_records_audit_log():
    db = _FakeDB(tenant_row=_eligible_tenant())
    await activate_trial(db, email="demo@sentry.mn")
    assert db.audit_params is not None
    assert db.audit_params["action"] == "trial_activated"
    assert db.audit_params["resource_type"] == "tenant"
    import json
    details = json.loads(db.audit_params["details"])
    assert "trial_ends_at" in details
    assert details["quota"]["max_cameras"] == 5


@pytest.mark.asyncio
async def test_activate_trial_rejects_missing_tenant():
    db = _FakeDB(tenant_row=None)
    with pytest.raises(TrialNotEligible):
        await activate_trial(db, email="nobody@sentry.mn")


@pytest.mark.asyncio
async def test_activate_trial_rejects_already_past_plan_step():
    tenant = _eligible_tenant()
    tenant["onboarding_step"] = "pending_payment"
    db = _FakeDB(tenant_row=tenant)
    with pytest.raises(TrialAlreadyActive):
        await activate_trial(db, email="demo@sentry.mn")


@pytest.mark.asyncio
async def test_activate_trial_rejects_completed_onboarding():
    tenant = _eligible_tenant()
    tenant["onboarding_step"] = "completed"
    db = _FakeDB(tenant_row=tenant)
    with pytest.raises(TrialAlreadyActive):
        await activate_trial(db, email="demo@sentry.mn")


@pytest.mark.asyncio
async def test_activate_trial_rejects_non_pending_status():
    tenant = _eligible_tenant()
    tenant["status"] = "suspended"
    db = _FakeDB(tenant_row=tenant)
    with pytest.raises(TrialNotEligible):
        await activate_trial(db, email="demo@sentry.mn")


@pytest.mark.asyncio
async def test_activate_trial_losing_race_raises_already_active():
    """UPDATE affects 0 rows because a concurrent request won — we
    surface `TrialAlreadyActive` so the handler emits a safe 400."""
    db = _FakeDB(tenant_row=_eligible_tenant(), update_rowcount=0)
    with pytest.raises(TrialAlreadyActive):
        await activate_trial(db, email="demo@sentry.mn")


@pytest.mark.asyncio
async def test_activate_trial_does_not_commit_on_race_loss():
    db = _FakeDB(tenant_row=_eligible_tenant(), update_rowcount=0)
    with pytest.raises(TrialAlreadyActive):
        await activate_trial(db, email="demo@sentry.mn")
    assert db.committed is False

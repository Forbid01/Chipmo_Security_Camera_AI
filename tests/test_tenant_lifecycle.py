"""Tests for T1-10 — tenant lifecycle state machine."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from shoplift_detector.app.services.tenant_lifecycle import (
    TENANT_STATUS_CHANGE_ACTION,
    VALID_TRANSITIONS,
    InvalidTransitionError,
    is_valid_transition,
    transition_tenant_status,
)


# ---------------------------------------------------------------------------
# Transition graph — pure predicates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frm,to", [
    ("pending", "active"),
    ("active", "suspended"),
    ("active", "grace"),
    ("suspended", "active"),
    ("suspended", "grace"),
    ("suspended", "churned"),
    ("grace", "active"),
    ("grace", "churned"),
])
def test_valid_transitions_are_allowed(frm, to):
    assert is_valid_transition(frm, to) is True


@pytest.mark.parametrize("frm,to", [
    # Idempotent self-transitions are rejected so audit logs stay clean.
    ("pending", "pending"),
    ("active", "active"),
    # Backwards jumps.
    ("active", "pending"),
    ("grace", "suspended"),
    # Terminal state has no outgoing edges.
    ("churned", "active"),
    ("churned", "grace"),
    # Pending can't skip straight to grace.
    ("pending", "grace"),
])
def test_invalid_transitions_are_rejected(frm, to):
    assert is_valid_transition(frm, to) is False


def test_churned_is_terminal():
    assert VALID_TRANSITIONS["churned"] == frozenset()


def test_every_non_terminal_state_has_outgoing_edges():
    for state in ("pending", "active", "suspended", "grace"):
        assert VALID_TRANSITIONS[state], f"{state} must have outgoing edges"


# ---------------------------------------------------------------------------
# Service function — happy path + error codes
# ---------------------------------------------------------------------------

class _CapturingDB:
    """Captures every SQL exchange so we can assert the UPDATE +
    audit INSERT fire in the same transaction."""

    def __init__(self, tenant_row=None, audit_id=1):
        self._tenant_row = tenant_row
        self._audit_id = audit_id
        self.update_query: str | None = None
        self.update_params: dict | None = None
        self.audit_query: str | None = None
        self.audit_params: dict | None = None
        self.committed = False

    async def execute(self, query, params=None):
        q = str(query)
        if "FROM tenants" in q and "SELECT" in q:
            return _FakeResult(row=self._tenant_row)
        if q.strip().startswith("UPDATE tenants"):
            self.update_query = q
            self.update_params = params
            return _FakeResult(rowcount=1)
        if "INSERT INTO audit_log" in q:
            self.audit_query = q
            self.audit_params = params
            return _FakeResult(row=(self._audit_id,))
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


@pytest.mark.asyncio
async def test_transition_writes_update_and_audit_and_commits():
    tid = uuid4()
    db = _CapturingDB(
        tenant_row={
            "tenant_id": tid,
            "status": "pending",
            "plan": "starter",
            "legal_name": "x",
            "display_name": "x",
            "email": "x@x",
            "phone": None,
            "created_at": None,
            "trial_ends_at": None,
            "current_period_end": None,
            "payment_method_id": None,
            "resource_quota": {},
        }
    )

    result = await transition_tenant_status(
        db,
        tenant_id=tid,
        new_status="active",
        actor_user_id=7,
        reason="pilot go-live",
    )

    assert result == {"tenant_id": str(tid), "from": "pending", "to": "active"}
    assert db.update_query is not None
    assert db.update_params["new_status"] == "active"
    assert db.audit_query is not None
    assert db.audit_params["action"] == TENANT_STATUS_CHANGE_ACTION
    assert db.audit_params["resource_type"] == "tenant"
    assert db.audit_params["user_id"] == 7
    # details is JSON-encoded for the JSONB cast.
    import json
    details = json.loads(db.audit_params["details"])
    assert details == {
        "from": "pending",
        "to": "active",
        "reason": "pilot go-live",
    }
    assert db.committed is True


@pytest.mark.asyncio
async def test_invalid_transition_raises_409_with_allowed_next():
    tid = uuid4()
    db = _CapturingDB(tenant_row={"tenant_id": tid, "status": "churned"})
    with pytest.raises(InvalidTransitionError) as ctx:
        await transition_tenant_status(
            db,
            tenant_id=tid,
            new_status="active",
            actor_user_id=1,
        )
    err: HTTPException = ctx.value
    assert err.status_code == 409
    assert err.detail["error"] == "invalid_status_transition"
    assert err.detail["current_status"] == "churned"
    assert err.detail["allowed_next"] == []  # churned is terminal


@pytest.mark.asyncio
async def test_unknown_new_status_raises_400():
    tid = uuid4()
    db = _CapturingDB(tenant_row={"tenant_id": tid, "status": "active"})
    with pytest.raises(HTTPException) as ctx:
        await transition_tenant_status(
            db,
            tenant_id=tid,
            new_status="vaporized",
            actor_user_id=1,
        )
    assert ctx.value.status_code == 400


@pytest.mark.asyncio
async def test_missing_tenant_raises_404():
    db = _CapturingDB(tenant_row=None)
    with pytest.raises(HTTPException) as ctx:
        await transition_tenant_status(
            db,
            tenant_id=uuid4(),
            new_status="active",
            actor_user_id=1,
        )
    assert ctx.value.status_code == 404


@pytest.mark.asyncio
async def test_reason_nullable_but_plumbs_through_to_audit():
    tid = uuid4()
    db = _CapturingDB(
        tenant_row={"tenant_id": tid, "status": "active", "plan": "pro"}
    )
    await transition_tenant_status(
        db, tenant_id=tid, new_status="suspended", actor_user_id=None
    )
    import json
    details = json.loads(db.audit_params["details"])
    assert details["reason"] is None

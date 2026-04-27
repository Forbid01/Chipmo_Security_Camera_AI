"""Tests for T2-08 — 7-day onboarding email sequence."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from shoplift_detector.app.services.email_sender import RecordingEmailSender
from shoplift_detector.app.services.onboarding_emails import (
    EMAIL_SCHEDULE,
    ONBOARDING_EMAIL_ACTION,
    day_0_welcome,
    day_12_trial_ending_soon,
    dispatch_due_emails,
    due_for_tenant,
)


def _tenant(created_ago_days: int = 0, **overrides):
    now = datetime.now(UTC)
    return {
        "tenant_id": uuid4(),
        "legal_name": "Номин",
        "display_name": "Номин",
        "email": "demo@sentry.mn",
        "created_at": now - timedelta(days=created_ago_days),
        **overrides,
    }


# ---------------------------------------------------------------------------
# Schedule shape
# ---------------------------------------------------------------------------

def test_schedule_has_seven_entries():
    # DoD: Day 0, 1, 2, 3, 5, 7, 12 — seven emails total.
    assert len(EMAIL_SCHEDULE) == 7


def test_schedule_days_match_doc():
    days = [entry.day for entry in EMAIL_SCHEDULE]
    assert days == [0, 1, 2, 3, 5, 7, 12]


def test_every_schedule_entry_has_label():
    # Labels are used for audit_log + funnel attribution — must be
    # unique so we can tell two sends apart.
    labels = [entry.label for entry in EMAIL_SCHEDULE]
    assert len(labels) == len(set(labels))


# ---------------------------------------------------------------------------
# Template builders — content contract
# ---------------------------------------------------------------------------

def test_day_zero_email_mentions_store_name_and_welcome():
    tenant = _tenant()
    msg = day_0_welcome(tenant)
    assert "Номин" in msg.text_body
    assert "тавтай морил" in msg.text_body.lower()
    assert f"t.me/sentry_bot?start={tenant['tenant_id']}" in msg.text_body
    assert msg.html_body is not None


def test_day_12_email_mentions_trial_ending():
    msg = day_12_trial_ending_soon(_tenant())
    assert "2 хоног" in msg.text_body


# ---------------------------------------------------------------------------
# due_for_tenant — scheduling predicate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("age,expected_days", [
    (0, [0]),
    (1, [1]),
    (2, [2]),
    (3, [3]),
    (4, []),      # no email on Day 4
    (5, [5]),
    (6, []),
    (7, [7]),
    (8, []),
    (12, [12]),
    (13, []),     # past Day 12 — cron stops
])
def test_due_days_for_tenant_age(age, expected_days):
    tenant = _tenant(created_ago_days=age)
    due = due_for_tenant(tenant, already_sent_days=frozenset())
    assert [e.day for e in due] == expected_days


def test_due_skips_already_sent_days():
    tenant = _tenant(created_ago_days=0)
    due = due_for_tenant(tenant, already_sent_days=frozenset({0}))
    assert due == []


def test_due_does_not_backfill_missed_days():
    """If the cron was down on Day 1, Day 5 still fires on schedule
    but Day 1 is NOT retroactively sent — the email would be stale."""
    tenant = _tenant(created_ago_days=5)
    # Day 0 already sent, Day 1 was missed — only Day 5 is due today.
    due = due_for_tenant(tenant, already_sent_days=frozenset({0}))
    assert [e.day for e in due] == [5]


# ---------------------------------------------------------------------------
# dispatch_due_emails — writes + sends
# ---------------------------------------------------------------------------

class _FakeDB:
    """Tracks audit_log rows and the SELECT used to look them up."""

    def __init__(self, existing_days=None):
        self._existing_days = existing_days or set()
        self.audit_inserts: list[dict] = []
        self.committed = False

    async def execute(self, query, params=None):
        q = str(query)
        if "FROM audit_log" in q and "action = :action" in q:
            rows = [
                {"details": {"day": d}} for d in self._existing_days
            ]
            return _FakeResult(rows=rows)
        if "INSERT INTO audit_log" in q:
            self.audit_inserts.append(params or {})
            return _FakeResult(row=(len(self.audit_inserts),))
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
async def test_dispatch_sends_today_and_writes_audit_log():
    db = _FakeDB()
    sender = RecordingEmailSender()
    labels = await dispatch_due_emails(
        db, tenant=_tenant(created_ago_days=0), email_sender=sender
    )
    assert labels == ["welcome"]
    assert len(sender.sent) == 1
    assert len(db.audit_inserts) == 1
    assert db.audit_inserts[0]["action"] == ONBOARDING_EMAIL_ACTION
    assert db.committed is True


@pytest.mark.asyncio
async def test_dispatch_does_not_send_when_already_sent():
    db = _FakeDB(existing_days={0})
    sender = RecordingEmailSender()
    labels = await dispatch_due_emails(
        db, tenant=_tenant(created_ago_days=0), email_sender=sender
    )
    assert labels == []
    assert sender.sent == []


@pytest.mark.asyncio
async def test_dispatch_empty_list_does_not_commit():
    db = _FakeDB(existing_days=set())
    sender = RecordingEmailSender()
    # Day 4 has no scheduled email.
    labels = await dispatch_due_emails(
        db, tenant=_tenant(created_ago_days=4), email_sender=sender
    )
    assert labels == []
    # No audit rows to write → no commit needed.
    assert db.audit_inserts == []


class _FailingSender:
    async def send(self, msg):
        raise RuntimeError("resend 500")


@pytest.mark.asyncio
async def test_dispatch_skips_audit_when_email_send_fails():
    db = _FakeDB()
    sender = _FailingSender()
    labels = await dispatch_due_emails(
        db, tenant=_tenant(created_ago_days=1), email_sender=sender
    )
    assert labels == []
    # The send failure must NOT be recorded as a sent email — so
    # the cron re-tries next day's run.
    assert db.audit_inserts == []

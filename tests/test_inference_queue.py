"""Tests for T1-09 — plan-priority GPU inference queue."""

import asyncio

import pytest

from shoplift_detector.app.services.inference_queue import (
    PLAN_PRIORITY,
    InferenceJob,
    PriorityInferenceQueue,
    UNKNOWN_PLAN_PRIORITY,
    priority_for_plan,
)


def _job(plan: str, *, tenant: str = "t", camera: int = 1) -> InferenceJob:
    return InferenceJob(
        tenant_id=tenant,
        camera_id=camera,
        plan=plan,
        submitted_at_monotonic=0.0,
    )


# ---------------------------------------------------------------------------
# Priority table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plan,priority", [
    ("enterprise", 0),
    ("pro", 1),
    ("starter", 2),
    ("trial", 3),
])
def test_plan_priority_matches_doc(plan, priority):
    assert PLAN_PRIORITY[plan] == priority


def test_priority_for_plan_unknown_falls_back_to_trial():
    assert priority_for_plan("unknown") == UNKNOWN_PLAN_PRIORITY
    assert priority_for_plan(None) == UNKNOWN_PLAN_PRIORITY


def test_priority_ordering_is_enterprise_first_trial_last():
    assert (
        PLAN_PRIORITY["enterprise"]
        < PLAN_PRIORITY["pro"]
        < PLAN_PRIORITY["starter"]
        < PLAN_PRIORITY["trial"]
    )


# ---------------------------------------------------------------------------
# Queue ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enterprise_is_dequeued_before_pro():
    q = PriorityInferenceQueue()
    q.put_nowait(_job("pro"))
    q.put_nowait(_job("enterprise"))
    assert (await q.get()).plan == "enterprise"
    assert (await q.get()).plan == "pro"


@pytest.mark.asyncio
async def test_pro_before_starter_before_trial():
    q = PriorityInferenceQueue()
    # Shuffle to prove we're sorting, not just FIFO-ing.
    q.put_nowait(_job("trial"))
    q.put_nowait(_job("starter"))
    q.put_nowait(_job("pro"))
    order = [(await q.get()).plan for _ in range(3)]
    assert order == ["pro", "starter", "trial"]


@pytest.mark.asyncio
async def test_ties_break_fifo_by_sequence():
    q = PriorityInferenceQueue()
    first = _job("pro", camera=1)
    second = _job("pro", camera=2)
    third = _job("pro", camera=3)
    q.put_nowait(first)
    q.put_nowait(second)
    q.put_nowait(third)
    cameras = [(await q.get()).camera_id for _ in range(3)]
    assert cameras == [1, 2, 3]


# ---------------------------------------------------------------------------
# Blocking semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_blocks_until_put():
    q = PriorityInferenceQueue()

    async def producer():
        await asyncio.sleep(0.01)
        q.put_nowait(_job("pro"))

    producer_task = asyncio.create_task(producer())
    # If get() didn't block, it'd raise IndexError immediately.
    job = await asyncio.wait_for(q.get(), timeout=1.0)
    await producer_task
    assert job.plan == "pro"


@pytest.mark.asyncio
async def test_pop_nowait_returns_none_on_empty():
    q = PriorityInferenceQueue()
    assert q.pop_nowait() is None


@pytest.mark.asyncio
async def test_peek_priority_does_not_mutate():
    q = PriorityInferenceQueue()
    q.put_nowait(_job("trial"))
    q.put_nowait(_job("enterprise"))
    assert q.peek_priority() == PLAN_PRIORITY["enterprise"]
    # Queue still has both jobs.
    assert len(q) == 2


def test_is_empty_and_len():
    q = PriorityInferenceQueue()
    assert q.is_empty()
    assert len(q) == 0
    q.put_nowait(_job("pro"))
    assert not q.is_empty()
    assert len(q) == 1


# ---------------------------------------------------------------------------
# InferenceJob.priority property
# ---------------------------------------------------------------------------

def test_inference_job_exposes_priority_via_plan():
    assert _job("enterprise").priority == 0
    assert _job("trial").priority == 3
    assert _job("mystery").priority == UNKNOWN_PLAN_PRIORITY

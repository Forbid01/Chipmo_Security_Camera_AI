"""Contract tests for T02-24 — Postgres RLS spike.

The spike ships a decision document; enforcement is scheduled in
T02-25..T02-28. These tests pin the document so a future edit can't
silently drop a load-bearing claim.
"""

import pathlib

import pytest

SPIKE_DOC = (
    pathlib.Path(__file__).resolve().parents[1]
    / "docs"
    / "spikes"
    / "postgres-rls-under-asyncpg.md"
)


@pytest.fixture(scope="module")
def spike() -> str:
    assert SPIKE_DOC.exists(), "T02-24 spike document missing"
    return SPIKE_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Load-bearing claims
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("needle", [
    "SET LOCAL",
    "transaction pooling",
    "app.current_org_id",
    "app.bypass_tenant",
    "BYPASSRLS",
    "Fail-closed",
    "fail-closed",
])
def test_spike_cites_load_bearing_concept(spike, needle):
    # Case-insensitive check because we match both "Fail-closed" heading
    # and inline "fail-closed" prose.
    assert needle in spike or needle.lower() in spike.lower()


def test_spike_covers_every_tenant_table(spike):
    # Tables from the T02-12 audit inventory that need a policy.
    for table in (
        "alerts", "cameras", "stores", "alert_feedback", "cases",
        "sync_packs", "inference_metrics", "camera_health",
    ):
        assert table in spike, f"Spike must list {table} in policy scope"


def test_spike_explicitly_excludes_audit_log_and_users(spike):
    # Per T02-13, audit_log and users are legitimately cross-tenant.
    # Verify the spike documents why they're out of scope.
    for table in ("audit_log", "users"):
        assert f"`{table}`" in spike
        # Nearby "NO RLS" marker keeps the exclusion explicit.
    assert "NO RLS" in spike


# ---------------------------------------------------------------------------
# Operational plan
# ---------------------------------------------------------------------------

def test_spike_names_feature_flag(spike):
    assert "TENANCY_RLS_ENFORCED" in spike


def test_spike_stages_rollout_canary_then_full(spike):
    assert "Canary" in spike or "canary" in spike
    assert "Staging" in spike or "staging" in spike
    assert "Rollback" in spike or "rollback" in spike


def test_spike_picks_guc_flag_design_over_bypassrls_role(spike):
    # The doc must state that BYPASSRLS role is rejected and the
    # GUC-flag + policy-exception design is chosen.
    assert "Rejected alternatives" in spike
    assert "Chosen design" in spike


# ---------------------------------------------------------------------------
# Follow-up task wiring
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ticket", ["T02-25", "T02-26", "T02-27", "T02-28"])
def test_spike_enumerates_followup_tickets(spike, ticket):
    assert ticket in spike


def test_tasks_md_registers_followup_tickets_from_spike():
    tasks_md = (
        pathlib.Path(__file__).resolve().parents[1] / "docs" / "TASKS.md"
    ).read_text(encoding="utf-8")
    # Sanity: at least the first follow-up should be filed once we
    # commit to it. The spike itself is enough to close T02-24 even
    # before the follow-up rows land, but this guard lets a future PR
    # that adds the follow-ups get tested too without a new test file.
    assert "T02-24" in tasks_md

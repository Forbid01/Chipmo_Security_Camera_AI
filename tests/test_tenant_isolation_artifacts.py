"""Contract tests for the T02-12 audit and T02-13 decision artifacts.

These don't execute isolation themselves — enforcement lands in T02-21 /
T02-22. They pin the output documents so a future refactor can't
accidentally drop a Critical finding or forget the decision.
"""

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT_DOC = REPO_ROOT / "docs" / "audits" / "multi-tenant-isolation-2026-04-21.md"
DECISION_DOC = (
    REPO_ROOT / "docs" / "decisions" / "2026-04-21-tenant-isolation-strategy.md"
)


@pytest.fixture(scope="module")
def audit() -> str:
    assert AUDIT_DOC.exists(), "T02-12 audit doc missing"
    return AUDIT_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def decision() -> str:
    assert DECISION_DOC.exists(), "T02-13 decision doc missing"
    return DECISION_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Audit doc — must name every Critical hazard + the full inventory
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("needle", [
    "H-H7", "H-H8", "H-H15",  # Critical video-feed hazards
    "H-H9", "H-H12",          # High feedback / telegram hazards
    "/api/v1/video/feed",     # path named explicitly
    "/api/v1/feedback",
    "/api/v1/telegram",
])
def test_audit_names_every_critical_and_high_hazard(audit, needle):
    assert needle in audit, f"Audit must call out {needle}"


def test_audit_covers_every_repository(audit):
    expected_repos = [
        "AlertRepository",
        "CameraRepository",
        "StoreRepository",
        "FeedbackRepository",
        "AlertStateRepository",
        "CaseRepository",
        "SyncPackRepository",
        "InferenceMetricRepository",
        "AuditLogRepository",
        "UserRepository",
    ]
    for repo in expected_repos:
        assert repo in audit, f"Audit missed {repo}"


def test_audit_lists_severity_summary(audit):
    # The summary table must show counts so reviewers see the shape.
    assert "Severity summary" in audit
    # At least one Critical finding was discovered — ensure we didn't
    # delete the row.
    assert re.search(r"Critical.*\|\s*\d+", audit), (
        "Severity summary must enumerate Critical count"
    )


def test_audit_has_concrete_remediation_plan(audit):
    assert "Remediation plan" in audit
    # The plan must link to T02-13 so the follow-up chain is visible.
    assert "T02-13" in audit


# ---------------------------------------------------------------------------
# Decision doc — must name the chosen strategy + follow-up tickets
# ---------------------------------------------------------------------------

def test_decision_picks_option_c_middleware_first(decision):
    # Document the exact wording so a silent switch is caught.
    assert "middleware now" in decision.lower() or "middleware first" in decision.lower()
    assert "Option C" in decision


@pytest.mark.parametrize("ticket", ["T02-21", "T02-22", "T02-23", "T02-24"])
def test_decision_enumerates_followup_tickets(decision, ticket):
    assert ticket in decision, f"Decision doc missing follow-up {ticket}"


def test_decision_names_the_404_vs_403_principle(decision):
    # 404 for unauthorized (blocks enumeration), 403 for same-org-wrong-role.
    assert "404" in decision and "403" in decision


def test_decision_references_the_audit_as_input(decision):
    assert "T02-12" in decision
    assert "multi-tenant-isolation" in decision


# ---------------------------------------------------------------------------
# TASKS.md — follow-ups are filed so they don't silently rot
# ---------------------------------------------------------------------------

def test_tasks_md_registers_followup_tickets():
    tasks_md = (REPO_ROOT / "docs" / "TASKS.md").read_text(encoding="utf-8")
    for ticket in ("T02-21", "T02-22", "T02-23", "T02-24"):
        assert ticket in tasks_md, (
            f"TASKS.md must register {ticket} so the remediation is tracked"
        )

"""Tests pinning the Chipmo Grafana overview dashboard (T02-11).

The dashboard JSON is provisioned via T02-10's Grafana container. These
tests don't hit Grafana — they parse the file and assert the structural
contract the dashboard owes its callers:
- datasource UIDs match the provisioned names
- every panel required by docs/03-TECH-SPECS.md §3.2 is present
- every PromQL expression references a metric name our app emits
  (T02-08 registry)
"""

import json
import pathlib

import pytest

from shoplift_detector.app.observability.metrics import registered_metric_names

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD_PATH = (
    REPO_ROOT
    / "observability"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "chipmo"
    / "chipmo-overview.json"
)


@pytest.fixture(scope="module")
def dashboard() -> dict:
    assert DASHBOARD_PATH.exists(), (
        "Chipmo overview dashboard JSON missing. Grafana's dashboard "
        "provider watches this folder (T02-10); the file must ship here."
    )
    return json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))


def _iter_panel_targets(panel: dict):
    yield from panel.get("targets", [])


def _collect_expressions(dashboard: dict) -> list[str]:
    exprs: list[str] = []
    for panel in dashboard["panels"]:
        for target in _iter_panel_targets(panel):
            expr = target.get("expr")
            if expr:
                exprs.append(expr)
    return exprs


def _collect_prometheus_expressions(dashboard: dict) -> list[str]:
    """Only expressions whose effective datasource is Prometheus.

    LogQL selectors in Loki panels (e.g. `{service="chipmo-backend"}`)
    are not PromQL and don't reference app metrics, so they shouldn't
    be validated against the T02-08 registry.
    """
    exprs: list[str] = []
    for panel in dashboard["panels"]:
        panel_ds = panel.get("datasource") or {}
        panel_ds_uid = panel_ds.get("uid") if isinstance(panel_ds, dict) else None
        for target in _iter_panel_targets(panel):
            target_ds = target.get("datasource") or {}
            target_ds_uid = (
                target_ds.get("uid") if isinstance(target_ds, dict) else None
            )
            effective_uid = target_ds_uid or panel_ds_uid
            if effective_uid != "chipmo-prometheus":
                continue
            expr = target.get("expr")
            if expr:
                exprs.append(expr)
    return exprs


# ---------------------------------------------------------------------------
# Top-level metadata
# ---------------------------------------------------------------------------

def test_dashboard_uid_and_title_are_stable(dashboard):
    # Stable UID lets URLs and alert rules reference this dashboard.
    assert dashboard["uid"] == "chipmo-overview"
    assert "Chipmo" in dashboard["title"]


def test_dashboard_declares_expected_datasource_uids(dashboard):
    seen: set[str] = set()
    for panel in dashboard["panels"]:
        ds = panel.get("datasource")
        if isinstance(ds, dict) and "uid" in ds:
            seen.add(ds["uid"])
        for target in _iter_panel_targets(panel):
            ds = target.get("datasource")
            if isinstance(ds, dict) and "uid" in ds:
                seen.add(ds["uid"])
    # T02-10 provisions exactly these two UIDs.
    assert seen.issubset({"chipmo-prometheus", "chipmo-loki"})
    assert "chipmo-prometheus" in seen, "At least one panel must query Prometheus"


def test_dashboard_has_store_and_camera_template_variables(dashboard):
    names = {v["name"] for v in dashboard["templating"]["list"]}
    assert names == {"store_id", "camera_id"}


# ---------------------------------------------------------------------------
# Panel coverage — every acceptance bullet from the task must appear
# ---------------------------------------------------------------------------

REQUIRED_PANEL_TOPICS = {
    "alert_rate": ["Alert rate"],
    "fp_rate": ["False positive rate", "FP rate"],
    "gpu_utilization": ["GPU utilization"],
    "gpu_memory": ["GPU memory"],
    "inference_latency": ["Inference latency"],
    "camera_uptime": ["Camera uptime"],
    "camera_fps": ["Camera FPS"],
}


@pytest.mark.parametrize("topic,needles", list(REQUIRED_PANEL_TOPICS.items()))
def test_dashboard_has_panel_for_topic(dashboard, topic, needles):
    titles = [p.get("title", "") for p in dashboard["panels"]]
    assert any(
        any(needle.lower() in t.lower() for needle in needles)
        for t in titles
    ), f"No panel titled for topic '{topic}'. Titles: {titles}"


def test_dashboard_uses_histogram_quantile_for_p50_p95_p99(dashboard):
    exprs = _collect_prometheus_expressions(dashboard)
    p50 = [e for e in exprs if "histogram_quantile(0.50" in e]
    p95 = [e for e in exprs if "histogram_quantile(0.95" in e]
    p99 = [e for e in exprs if "histogram_quantile(0.99" in e]
    assert p50 and p95 and p99, (
        "Inference latency panel must expose p50, p95, and p99 quantiles"
    )


def test_dashboard_has_loki_logs_panel(dashboard):
    log_panels = [p for p in dashboard["panels"] if p.get("type") == "logs"]
    assert log_panels, "Dashboard must ship at least one Loki logs panel"
    for panel in log_panels:
        ds = panel.get("datasource", {})
        assert ds.get("uid") == "chipmo-loki"


# ---------------------------------------------------------------------------
# PromQL sanity — every referenced metric must be one our app emits
# ---------------------------------------------------------------------------

def test_every_prom_metric_referenced_is_registered():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    exprs = _collect_prometheus_expressions(dashboard)

    known = set(registered_metric_names())
    # Histogram metrics expose derived series _bucket/_sum/_count that
    # PromQL uses for quantiles. Accept those suffixes too.
    derived = set()
    for name in known:
        derived.update({f"{name}_bucket", f"{name}_sum", f"{name}_count"})

    metric_tokens = known | derived

    for expr in exprs:
        matched = any(token in expr for token in metric_tokens)
        assert matched, (
            f"Dashboard expression references no registered Chipmo metric: "
            f"{expr!r}\nKnown metrics: {sorted(known)}"
        )


# ---------------------------------------------------------------------------
# FP rate formula sanity — guards against accidental divide-by-zero
# ---------------------------------------------------------------------------

def test_fp_rate_panel_protects_against_zero_denominator(dashboard):
    fp_panel = next(
        p for p in dashboard["panels"]
        if "False positive rate" in p.get("title", "")
    )
    expr = fp_panel["targets"][0]["expr"]
    # clamp_min(..., 1) keeps the denominator ≥ 1 when there are no alerts
    # in the window; otherwise Grafana shows NaN spikes right after startup.
    assert "clamp_min(" in expr, (
        "FP rate must clamp its denominator; cold windows produce NaN otherwise"
    )


def test_dashboard_template_variables_use_regex_all(dashboard):
    for var in dashboard["templating"]["list"]:
        assert var["includeAll"] is True
        assert var["allValue"] == ".+"

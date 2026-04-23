"""Tests pinning the observability stack config (T02-10).

We don't run Docker in the test process, but we do want to catch
regressions in the compose/scrape/datasource wiring — a typo in a
service name or a drift between the scrape target and the app port
would silently break the /metrics → dashboard path.

Each test is a parse-and-assert over the YAML files shipped in
`observability/` and `docker-compose.observability.yml`.
"""

import pathlib

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover — yaml ships with most envs
    yaml = None


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "docker-compose.observability.yml"
PROMETHEUS_CONFIG = REPO_ROOT / "observability" / "prometheus.yml"
LOKI_CONFIG = REPO_ROOT / "observability" / "loki" / "loki-config.yml"
PROMTAIL_CONFIG = REPO_ROOT / "observability" / "promtail" / "promtail-config.yml"
GRAFANA_DATASOURCES = (
    REPO_ROOT
    / "observability"
    / "grafana"
    / "provisioning"
    / "datasources"
    / "datasources.yml"
)
GRAFANA_DASHBOARD_PROVIDER = (
    REPO_ROOT
    / "observability"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "dashboards.yml"
)


@pytest.fixture(scope="module")
def compose() -> dict:
    if yaml is None:
        pytest.skip("PyYAML not installed")
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# docker-compose.observability.yml
# ---------------------------------------------------------------------------

def test_compose_file_declares_all_four_services(compose):
    services = compose["services"]
    assert set(services.keys()) == {"prometheus", "loki", "promtail", "grafana"}


@pytest.mark.parametrize("service,port", [
    ("prometheus", "9090:9090"),
    ("loki", "3100:3100"),
    ("grafana", "3001:3000"),
])
def test_compose_exposes_expected_host_ports(compose, service, port):
    ports = compose["services"][service].get("ports", [])
    assert port in ports, f"{service} missing host mapping {port}; got {ports}"


def test_promtail_has_no_published_ports(compose):
    # Log shipper; nothing to expose on the host. Guard against someone
    # accidentally publishing the internal 9080.
    ports = compose["services"]["promtail"].get("ports")
    assert not ports, f"promtail should not publish ports, got {ports}"


def test_grafana_has_admin_and_analytics_defaults(compose):
    env = compose["services"]["grafana"]["environment"]
    joined = "\n".join(env)
    assert "GF_SECURITY_ADMIN_USER=" in joined
    assert "GF_SECURITY_ADMIN_PASSWORD=" in joined
    assert "GF_ANALYTICS_REPORTING_ENABLED=false" in joined
    assert "GF_USERS_ALLOW_SIGN_UP=false" in joined


def test_compose_network_is_bridge_named_chipmo_net(compose):
    networks = compose["networks"]
    assert "chipmo-net" in networks
    assert networks["chipmo-net"]["driver"] == "bridge"


def test_prometheus_mounts_config_read_only(compose):
    volumes = compose["services"]["prometheus"]["volumes"]
    assert any(
        "prometheus.yml:/etc/prometheus/prometheus.yml:ro" in v
        for v in volumes
    )


def test_promtail_mounts_docker_socket_read_only(compose):
    # Socket mount is what gives promtail access to container logs.
    # Must be :ro so a compromise in the log shipper can't control the
    # Docker daemon.
    volumes = compose["services"]["promtail"]["volumes"]
    assert any(
        "/var/run/docker.sock:/var/run/docker.sock:ro" in v for v in volumes
    )


def test_grafana_provisioning_mount_points_at_repo_tree(compose):
    volumes = compose["services"]["grafana"]["volumes"]
    assert any(
        "./observability/grafana/provisioning:/etc/grafana/provisioning:ro" in v
        for v in volumes
    )


# ---------------------------------------------------------------------------
# prometheus.yml — scrape config
# ---------------------------------------------------------------------------

def test_prometheus_scrape_config_targets_app_backend():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    cfg = yaml.safe_load(PROMETHEUS_CONFIG.read_text(encoding="utf-8"))

    jobs = {job["job_name"]: job for job in cfg["scrape_configs"]}
    assert "chipmo-backend" in jobs

    backend = jobs["chipmo-backend"]
    assert backend.get("metrics_path", "/metrics") == "/metrics"
    target_sets = backend["static_configs"]
    flat_targets = [t for s in target_sets for t in s["targets"]]
    assert "app:8000" in flat_targets, (
        f"backend scrape target must match app container port; got {flat_targets}"
    )


def test_prometheus_reserves_edge_job_for_phase_7():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    cfg = yaml.safe_load(PROMETHEUS_CONFIG.read_text(encoding="utf-8"))
    jobs = {job["job_name"] for job in cfg["scrape_configs"]}
    assert "chipmo-edge" in jobs


# ---------------------------------------------------------------------------
# loki-config.yml
# ---------------------------------------------------------------------------

def test_loki_config_disables_auth_and_listens_on_3100():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    cfg = yaml.safe_load(LOKI_CONFIG.read_text(encoding="utf-8"))
    assert cfg["auth_enabled"] is False
    assert cfg["server"]["http_listen_port"] == 3100


def test_loki_uses_filesystem_storage_in_dev():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    cfg = yaml.safe_load(LOKI_CONFIG.read_text(encoding="utf-8"))
    storage = cfg["common"]["storage"]
    assert "filesystem" in storage


# ---------------------------------------------------------------------------
# promtail-config.yml
# ---------------------------------------------------------------------------

def test_promtail_pushes_to_loki_service_dns():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    cfg = yaml.safe_load(PROMTAIL_CONFIG.read_text(encoding="utf-8"))
    urls = [c["url"] for c in cfg["clients"]]
    assert "http://loki:3100/loki/api/v1/push" in urls


# ---------------------------------------------------------------------------
# Grafana provisioning
# ---------------------------------------------------------------------------

def test_grafana_provisions_prometheus_and_loki_datasources():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    cfg = yaml.safe_load(GRAFANA_DATASOURCES.read_text(encoding="utf-8"))
    by_type = {ds["type"]: ds for ds in cfg["datasources"]}
    assert "prometheus" in by_type
    assert "loki" in by_type
    # UIDs must be stable so dashboards can reference them.
    assert by_type["prometheus"]["uid"] == "chipmo-prometheus"
    assert by_type["loki"]["uid"] == "chipmo-loki"
    # Prometheus should be the default datasource.
    assert by_type["prometheus"].get("isDefault") is True


def test_grafana_dashboard_provider_watches_expected_folder():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    cfg = yaml.safe_load(GRAFANA_DASHBOARD_PROVIDER.read_text(encoding="utf-8"))
    providers = cfg["providers"]
    assert len(providers) == 1
    provider = providers[0]
    assert provider["folder"] == "Chipmo"
    assert provider["options"]["path"].endswith("/dashboards/chipmo")


def test_dashboard_drop_folder_exists_for_t02_11():
    folder = (
        REPO_ROOT
        / "observability"
        / "grafana"
        / "provisioning"
        / "dashboards"
        / "chipmo"
    )
    assert folder.is_dir(), (
        "T02-11 drops dashboard JSON here; the folder must exist so the "
        "Grafana provisioning container can mount it."
    )

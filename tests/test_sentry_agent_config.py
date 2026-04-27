"""Tests for the Sentry edge agent config loader + CLI (T4-01).

The Docker image cannot boot without a working config resolver, so
these tests guard the env-vs-YAML precedence and the CLI plumbing
that `Dockerfile ENTRYPOINT` depends on.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

# Agent package lives outside the backend tree — extend sys.path so
# pytest can import it without an editable install.
AGENT_ROOT = Path(__file__).resolve().parents[1] / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch):
    """Every test gets a clean SENTRY_* env surface so host env can't
    leak into assertions about precedence."""
    for key in list(os.environ):
        if key.startswith("SENTRY_"):
            monkeypatch.delenv(key, raising=False)


def test_version_matches_pyproject():
    import sentry_agent

    assert sentry_agent.__version__ == "0.1.0"


def test_load_config_from_env(monkeypatch):
    from sentry_agent.config import load_config

    env = {
        "SENTRY_SERVER_URL": "https://api.sentry.mn/",
        "SENTRY_API_KEY": "sk_live_envkey_abcdef123456",
        "SENTRY_TENANT_ID": "11111111-2222-3333-4444-555555555555",
    }
    cfg = load_config(env=env, config_path=Path("/nonexistent.yaml"))

    # URL trailing slash trimmed so downstream calls don't build `//alerts`.
    assert cfg.server_url == "https://api.sentry.mn"
    assert cfg.api_key == "sk_live_envkey_abcdef123456"
    assert cfg.tenant_id == "11111111-2222-3333-4444-555555555555"
    assert cfg.heartbeat_interval_s == 60
    assert cfg.config_source == "env"


def test_load_config_from_yaml_file(tmp_path):
    from sentry_agent.config import load_config

    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                'server_url: "https://api.sentry.mn"',
                'api_key: "sk_live_filekey_9876543210"',
                'tenant_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"',
                "heartbeat_interval_s: 90",
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(env={}, config_path=yaml_path)
    assert cfg.api_key == "sk_live_filekey_9876543210"
    assert cfg.heartbeat_interval_s == 90
    assert cfg.config_source == f"file:{yaml_path}"


def test_env_overrides_yaml(tmp_path):
    """Env wins over YAML — lets ops rotate a leaked key without
    rebuilding the image."""
    from sentry_agent.config import load_config

    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                'server_url: "https://old.example.com"',
                'api_key: "sk_live_old_key_value_here"',
                'tenant_id: "old-tenant"',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(
        env={
            "SENTRY_SERVER_URL": "https://new.sentry.mn",
            "SENTRY_API_KEY": "sk_live_new_rotation_key",
            "SENTRY_TENANT_ID": "new-tenant",
        },
        config_path=yaml_path,
    )

    assert cfg.server_url == "https://new.sentry.mn"
    assert cfg.api_key == "sk_live_new_rotation_key"
    assert cfg.tenant_id == "new-tenant"


def test_missing_config_reports_all_fields():
    """Listing every missing field up-front keeps the installer UX
    tight — users fix one config pass instead of N."""
    from sentry_agent.config import ConfigError, load_config

    with pytest.raises(ConfigError) as exc_info:
        load_config(env={}, config_path=Path("/nonexistent.yaml"))

    message = str(exc_info.value)
    assert "SENTRY_SERVER_URL" in message
    assert "SENTRY_API_KEY" in message
    assert "SENTRY_TENANT_ID" in message


def test_invalid_heartbeat_int_rejected(tmp_path):
    from sentry_agent.config import ConfigError, load_config

    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                'server_url: "https://api.sentry.mn"',
                'api_key: "sk_live_x"',
                'tenant_id: "t"',
                'heartbeat_interval_s: "not-a-number"',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="heartbeat_interval_s"):
        load_config(env={}, config_path=yaml_path)


def test_redact_masks_api_key(tmp_path):
    from sentry_agent.config import load_config

    cfg = load_config(
        env={
            "SENTRY_SERVER_URL": "https://x",
            "SENTRY_API_KEY": "sk_live_supersecretkey_dontleak",
            "SENTRY_TENANT_ID": "t",
        },
        config_path=tmp_path / "absent.yaml",
    )
    redacted = cfg.redact()
    # Raw secret must not appear in the redacted form — we log this dict.
    assert "supersecretkey" not in redacted["api_key"]
    assert redacted["api_key"].startswith("sk_live_")
    assert redacted["api_key"].endswith("leak")


def test_cli_version_command(capsys):
    from sentry_agent.cli import main

    exit_code = main(["version"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_cli_run_with_missing_config_exits_2(capsys, monkeypatch, tmp_path):
    from sentry_agent.cli import main

    missing = tmp_path / "definitely_not_here.yaml"
    exit_code = main(["run", "--config", str(missing), "--stop-after", "0"])
    # Exit 2 = config error. A non-zero code is what systemd / Docker
    # use to decide whether to restart the container.
    assert exit_code == 2
    stderr = capsys.readouterr().err
    assert "config error" in stderr


def test_cli_run_smoke_with_env(monkeypatch):
    """End-to-end: env-only config → runner → stop-after → clean exit."""
    from sentry_agent.cli import main

    monkeypatch.setenv("SENTRY_SERVER_URL", "https://api.sentry.mn")
    monkeypatch.setenv("SENTRY_API_KEY", "sk_live_xyz1234567890abcdef")
    monkeypatch.setenv("SENTRY_TENANT_ID", "11111111-1111-1111-1111-111111111111")

    # stop-after=0 makes the runner loop exit on first tick.
    exit_code = main(["run", "--stop-after", "0"])
    assert exit_code == 0


def test_cli_rejects_unknown_command(capsys):
    from sentry_agent.cli import main

    with pytest.raises(SystemExit):
        main(["frobnicate"])

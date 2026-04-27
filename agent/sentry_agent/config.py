"""Agent config loader — env-first, YAML-second.

The Docker image receives its config from two sources:

1. Environment variables (`SENTRY_SERVER_URL`, `SENTRY_API_KEY`,
   `SENTRY_TENANT_ID`). These win and are the default path for
   orchestrated deploys.
2. A YAML file (`/etc/sentry-agent/config.yaml` by default). Used
   for on-prem installs driven by the installer bundles from T4-03
   / T4-04.

Env overrides the file so ops can redeploy with new credentials
without touching a baked image.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("/etc/sentry-agent/config.yaml")


@dataclass(frozen=True)
class AgentConfig:
    server_url: str
    api_key: str
    tenant_id: str
    heartbeat_interval_s: int = 60
    config_source: str = "env"

    def redact(self) -> dict[str, Any]:
        """Return the config with the API key masked, for logging."""
        key = self.api_key
        masked = f"{key[:8]}…{key[-4:]}" if len(key) > 16 else "***"
        return {
            "server_url": self.server_url,
            "tenant_id": self.tenant_id,
            "api_key": masked,
            "heartbeat_interval_s": self.heartbeat_interval_s,
            "config_source": self.config_source,
        }


class ConfigError(RuntimeError):
    """Raised when required config values are missing or malformed."""


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    # Lazy import — PyYAML is an optional edge-only dep and we don't
    # want import-time failures for callers who only use env config.
    import yaml  # type: ignore[import-untyped]

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config at {path} must be a YAML mapping")
    return data


def load_config(
    *,
    env: dict[str, str] | None = None,
    config_path: Path | None = None,
) -> AgentConfig:
    """Resolve agent config from env (preferred) + YAML fallback.

    Raises ConfigError with a user-facing message when required
    fields are missing — the installer or orchestrator surfaces this
    as a startup failure.
    """
    env = env if env is not None else dict(os.environ)
    path = config_path if config_path is not None else DEFAULT_CONFIG_PATH
    file_cfg = _read_yaml(path)

    def pick(env_key: str, yaml_key: str) -> str | None:
        value = env.get(env_key)
        if value:
            return value
        fallback = file_cfg.get(yaml_key)
        return str(fallback) if fallback is not None else None

    server_url = pick("SENTRY_SERVER_URL", "server_url")
    api_key = pick("SENTRY_API_KEY", "api_key")
    tenant_id = pick("SENTRY_TENANT_ID", "tenant_id")

    missing = [
        name
        for name, value in (
            ("SENTRY_SERVER_URL", server_url),
            ("SENTRY_API_KEY", api_key),
            ("SENTRY_TENANT_ID", tenant_id),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            "Missing required config: " + ", ".join(missing) + f" (checked env + {path})"
        )

    heartbeat_raw = env.get("SENTRY_HEARTBEAT_INTERVAL_S") or file_cfg.get(
        "heartbeat_interval_s", 60
    )
    try:
        heartbeat = int(heartbeat_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"heartbeat_interval_s must be an integer, got {heartbeat_raw!r}"
        ) from exc

    source = "env" if env.get("SENTRY_API_KEY") else f"file:{path}"

    assert server_url and api_key and tenant_id  # narrowed above
    return AgentConfig(
        server_url=server_url.rstrip("/"),
        api_key=api_key,
        tenant_id=tenant_id,
        heartbeat_interval_s=heartbeat,
        config_source=source,
    )

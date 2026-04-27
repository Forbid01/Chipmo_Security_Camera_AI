"""Static validation of the Linux installer bundle (T4-04).

Mirrors T4-03's Windows tests — we can't run systemd or install
Docker in pytest, so we pin the *contract* of the files that the
CI and downstream deployment infra depend on:

* install.sh parses with `bash -n`, has all documented flags,
  performs Docker detect + cosign verify + config download + systemd
  enable, and its --uninstall path is reachable.
* sentry-agent.service carries the Required/After docker, Type,
  Restart, ExecStart, and hardening directives.
* The GitHub Actions workflow lints with shellcheck, runs
  systemd-analyze verify, emits SHA256SUMS, and attaches the
  bundle on tag pushes.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = ROOT / "agent" / "installer" / "linux"

INSTALL_SH = INSTALLER_DIR / "install.sh"
UNINSTALL_SH = INSTALLER_DIR / "uninstall.sh"
UNIT_FILE = INSTALLER_DIR / "sentry-agent.service"
README = INSTALLER_DIR / "README.md"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "agent-installer-linux.yml"


# ---------------------------------------------------------------------------
# install.sh — content + syntax
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def install_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


class TestInstallScript:
    def test_file_exists_and_executable_shebang(self, install_text):
        assert INSTALL_SH.exists()
        assert install_text.startswith("#!/usr/bin/env bash\n")

    def test_strict_mode_on(self, install_text):
        """set -Eeuo pipefail gives us fail-closed shell semantics —
        without it a silently-failing curl would leave a half-written
        config and a broken install."""
        assert "set -Eeuo pipefail" in install_text

    @pytest.mark.parametrize("flag", [
        "--config-url",
        "--image",
        "--no-verify-cosign",
        "--uninstall",
        "--help",
    ])
    def test_documented_flag_parsed(self, install_text, flag):
        assert flag in install_text

    @pytest.mark.parametrize("env_var", ["SENTRY_CONFIG_URL", "SENTRY_IMAGE"])
    def test_env_fallbacks_present(self, install_text, env_var):
        """Env-fallback is the non-interactive path used by cfgmgmt
        (Ansible, cloud-init). Dropping it breaks automated installs."""
        assert env_var in install_text

    def test_docker_detect_and_install(self, install_text):
        assert "detect_docker" in install_text
        assert "install_docker" in install_text
        # get.docker.com is the upstream-recommended one-liner entrypoint.
        assert "https://get.docker.com" in install_text
        assert "systemctl enable --now docker" in install_text

    def test_cosign_verification_path(self, install_text):
        assert "cosign verify" in install_text
        assert "certificate-identity-regexp" in install_text
        assert "certificate-oidc-issuer" in install_text

    def test_config_permissions_hardening(self, install_text):
        """config.yaml holds the raw API key — must be 0600 root:root
        and written via an atomic rename."""
        assert "chmod 0600" in install_text
        assert "chown root:root" in install_text
        # Atomic rename via mktemp + mv prevents half-written configs.
        assert "mktemp" in install_text
        assert "mv -f" in install_text

    def test_systemd_unit_written_and_enabled(self, install_text):
        # Path is interpolated from ${SERVICE_NAME} — assert on the
        # composing parts rather than the concrete literal.
        assert '/etc/systemd/system/${SERVICE_NAME}.service' in install_text
        assert 'SERVICE_NAME="sentry-agent"' in install_text
        assert "systemctl daemon-reload" in install_text
        assert "systemctl enable" in install_text
        assert "systemctl restart" in install_text

    def test_uninstall_preserves_config(self, install_text):
        assert "uninstall()" in install_text
        assert "systemctl stop" in install_text
        assert "systemctl disable" in install_text
        # Config dir preservation is the documented behavior — the
        # script must NOT rm -rf /etc/sentry-agent.
        assert "rm -rf /etc/sentry-agent" not in install_text
        assert "preserved" in install_text.lower()

    def test_root_guard(self, install_text):
        """Non-root run must die before touching /etc/systemd."""
        assert "need_root" in install_text
        assert 'id -u' in install_text

    def test_bash_n_syntax_check(self, tmp_path):
        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("bash not available on this runner")
        result = subprocess.run(
            [bash, "-n", str(INSTALL_SH)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"bash -n failed on install.sh:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# uninstall.sh
# ---------------------------------------------------------------------------

class TestUninstallScript:
    def test_delegates_to_install_sh(self):
        body = UNINSTALL_SH.read_text(encoding="utf-8")
        # Keeping tear-down logic in one place — uninstall.sh is a
        # 5-line wrapper that execs install.sh --uninstall.
        assert "install.sh --uninstall" in body
        assert body.startswith("#!/usr/bin/env bash")
        assert "set -Eeuo pipefail" in body

    def test_bash_n_syntax(self, tmp_path):
        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("bash not available")
        result = subprocess.run(
            [bash, "-n", str(UNINSTALL_SH)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# systemd unit
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def unit_text() -> str:
    return UNIT_FILE.read_text(encoding="utf-8")


class TestSystemdUnit:
    @pytest.mark.parametrize("section", ["[Unit]", "[Service]", "[Install]"])
    def test_sections_present(self, unit_text, section):
        assert section in unit_text

    @pytest.mark.parametrize("directive", [
        "Description=",
        "Requires=docker.service",
        "After=docker.service",
        "Type=simple",
        "Restart=always",
        "RestartSec=",
        "ExecStartPre=",
        "ExecStart=",
        "ExecStop=",
        "WantedBy=multi-user.target",
    ])
    def test_required_directive(self, unit_text, directive):
        assert directive in unit_text

    @pytest.mark.parametrize("hardening", [
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ReadWritePaths=",
        "ProtectHome=true",
    ])
    def test_security_hardening(self, unit_text, hardening):
        """These directives limit blast radius if the agent binary or
        the docker CLI develops a privilege-escalation bug."""
        assert hardening in unit_text

    def test_image_placeholder_substituted_at_install_time(self, unit_text):
        """`@SENTRY_IMAGE@` sentinel must be present in the committed
        unit so install.sh's `sed` pass has something to replace."""
        assert "@SENTRY_IMAGE@" in unit_text

    def test_config_mounted_readonly(self, unit_text):
        """config.yaml carries the API key — never let the container
        mutate it."""
        assert "/etc/sentry-agent/config.yaml:/etc/sentry-agent/config.yaml:ro" in unit_text


# ---------------------------------------------------------------------------
# README documents checksum pattern
# ---------------------------------------------------------------------------

def test_readme_documents_sha256_verification():
    body = README.read_text(encoding="utf-8")
    assert "sha256sum -c install.sh.sha256" in body
    # Required since DoD calls out `curl | bash pattern` + `checksum-verified`.
    assert "install.sh.sha256" in body


# ---------------------------------------------------------------------------
# GitHub Actions workflow shape
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


class TestLinuxInstallerWorkflow:
    def test_workflow_file_exists(self):
        assert WORKFLOW_PATH.exists()

    def test_triggers(self, workflow):
        triggers = workflow.get("on") or workflow.get(True)
        assert "push" in triggers
        assert "pull_request" in triggers
        assert "workflow_dispatch" in triggers
        assert "agent-v*" in triggers["push"].get("tags", [])

    def test_validate_job_runs_shellcheck_and_systemd_analyze(self, workflow):
        validate = workflow["jobs"]["validate"]
        assert validate["runs-on"] == "ubuntu-latest"
        steps = validate["steps"]
        names = [s.get("name", "") for s in steps]
        assert any("shellcheck" in n.lower() for n in names), names
        assert any("syntax" in n.lower() or "bash -n" in n.lower() for n in names), names
        assert any("systemd" in n.lower() for n in names), names

    def test_package_job_emits_sha256sums(self, workflow):
        package = workflow["jobs"]["package"]
        assert package["needs"] == ["validate"] or "validate" in package["needs"]
        steps = package["steps"]
        sha_step = next(s for s in steps if "SHA256SUMS" in s.get("name", ""))
        # Both per-file sidecars (*.sha256) and the combined manifest
        # must be generated so customers can verify either way.
        run = sha_step.get("run", "")
        assert "sha256sum" in run
        assert "SHA256SUMS" in run

    def test_package_job_gpg_sign_is_secret_gated(self, workflow):
        package = workflow["jobs"]["package"]
        gpg_step = next(
            s for s in package["steps"]
            if "GPG sign" in s.get("name", "")
        )
        # Must not crash on fork PRs — GPG secret absent path stays
        # green but skipped.
        assert "GPG_PRIVATE_KEY" in gpg_step["if"]

    def test_release_asset_upload_on_tag(self, workflow):
        package = workflow["jobs"]["package"]
        release_step = next(
            s for s in package["steps"]
            if "Attach to release" in s.get("name", "")
        )
        assert release_step["if"].startswith("startsWith(github.ref, 'refs/tags/agent-v')")
        files = release_step["with"]["files"]
        assert "install.sh" in files
        assert "SHA256SUMS" in files

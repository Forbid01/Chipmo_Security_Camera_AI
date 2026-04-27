"""Static validation of the macOS installer bundle (T4-05).

Full pkgbuild / productbuild can only run on a macOS runner, so
these tests pin the *contract* instead:

* build.sh accepts --version + --image + --sign-identity and calls
  pkgbuild+productbuild with the right arguments.
* Preinstall stops the LaunchDaemon before overwrite; postinstall
  creates /etc/sentry-agent with hardened perms and loads the daemon.
* LaunchDaemon plist carries Label/Program/RunAtLoad/KeepAlive and
  parameterizes the image reference.
* run-agent.sh mirrors the Linux/Windows foreground-docker-run
  pattern so launchd owns restart policy.
* CI workflow gates signing + notarization on their respective
  secrets and publishes the asset on tag push.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = ROOT / "agent" / "installer" / "macos"

BUILD_SH = INSTALLER_DIR / "build.sh"
RUN_AGENT = INSTALLER_DIR / "run-agent.sh"
UNINSTALL = INSTALLER_DIR / "uninstall.sh"
PREINSTALL = INSTALLER_DIR / "scripts" / "preinstall"
POSTINSTALL = INSTALLER_DIR / "scripts" / "postinstall"
PLIST = INSTALLER_DIR / "mn.sentry.agent.plist"
CASK = INSTALLER_DIR / "sentry-agent.rb"
WORKFLOW = ROOT / ".github" / "workflows" / "agent-installer-macos.yml"


# ---------------------------------------------------------------------------
# build.sh — CLI shape + core commands
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def build_text() -> str:
    return BUILD_SH.read_text(encoding="utf-8")


class TestBuildScript:
    def test_exists_and_strict(self, build_text):
        assert build_text.startswith("#!/usr/bin/env bash\n")
        assert "set -Eeuo pipefail" in build_text

    @pytest.mark.parametrize("flag", ["--version", "--image", "--sign-identity"])
    def test_documented_flags(self, build_text, flag):
        assert flag in build_text

    def test_calls_pkgbuild_and_productbuild(self, build_text):
        assert "pkgbuild" in build_text
        assert "productbuild" in build_text
        assert "--identifier \"mn.sentry.agent\"" in build_text
        assert "--install-location \"/\"" in build_text

    def test_requires_version(self, build_text):
        """Missing --version must exit before running pkgbuild."""
        assert '[ -n "$VERSION" ]' in build_text

    def test_sign_identity_optional(self, build_text):
        """productsign only runs when --sign-identity was supplied."""
        assert "productsign" in build_text
        assert 'if [ -n "$SIGN_IDENTITY" ]' in build_text

    def test_bash_n_syntax(self):
        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("bash not available")
        result = subprocess.run(
            [bash, "-n", str(BUILD_SH)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# LaunchDaemon plist
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plist_text() -> str:
    return PLIST.read_text(encoding="utf-8")


class TestLaunchDaemonPlist:
    def test_parses_as_valid_plist(self, plist_text):
        # Substitute the build-time placeholder so plistlib doesn't
        # choke on un-interpolated tokens. We still check for the
        # placeholder separately below.
        resolved = plist_text.replace("@SENTRY_IMAGE@", "ghcr.io/x/y:z").replace(
            "@SENTRY_VERSION@", "0.1.0"
        )
        data = plistlib.loads(resolved.encode("utf-8"))
        assert data["Label"] == "mn.sentry.agent"
        assert data["Program"] == "/usr/local/sentry-agent/run-agent.sh"
        assert data["RunAtLoad"] is True
        assert data["KeepAlive"] == {"SuccessfulExit": False}
        assert data["ThrottleInterval"] == 10

    def test_image_placeholder_present(self, plist_text):
        """build.sh substitutes `@SENTRY_IMAGE@` — the placeholder must
        exist in the committed template."""
        assert "@SENTRY_IMAGE@" in plist_text

    def test_logs_redirected_to_var_log(self, plist_text):
        assert "/var/log/sentry-agent/agent.log" in plist_text
        assert "/var/log/sentry-agent/agent.err" in plist_text


# ---------------------------------------------------------------------------
# Runtime + lifecycle scripts
# ---------------------------------------------------------------------------

class TestRunAgent:
    def test_docker_run_foreground(self):
        body = RUN_AGENT.read_text(encoding="utf-8")
        # `exec` so launchd sees docker's exit status directly.
        assert "exec docker run" in body
        assert "--init" in body
        assert "--rm" in body
        assert "--name \"$CONTAINER_NAME\"" in body
        # Config must be mounted read-only — carries the API key.
        assert ":/etc/sentry-agent/config.yaml:ro" in body

    def test_missing_config_exits_with_sleep(self):
        """Agent must not hot-loop launchd restarts when config.yaml
        is missing — a 60s sleep gives the postinstall path time to
        place the file."""
        body = RUN_AGENT.read_text(encoding="utf-8")
        assert "sleep 60" in body
        assert "exit 2" in body


class TestPreinstall:
    def test_checks_macos_version(self):
        body = PREINSTALL.read_text(encoding="utf-8")
        assert "sw_vers -productVersion" in body
        assert "-lt 12" in body

    def test_stops_existing_daemon(self):
        body = PREINSTALL.read_text(encoding="utf-8")
        assert "launchctl bootout system/mn.sentry.agent" in body


class TestPostinstall:
    def test_creates_config_dir_with_hardened_perms(self):
        body = POSTINSTALL.read_text(encoding="utf-8")
        assert "install -d -m 0750 -o root -g wheel /etc/sentry-agent" in body

    def test_detects_docker_before_running(self):
        body = POSTINSTALL.read_text(encoding="utf-8")
        assert "command -v docker" in body
        assert "docker info" in body

    def test_brew_cask_fallback(self):
        body = POSTINSTALL.read_text(encoding="utf-8")
        # Homebrew cask install — DoD calls out "Homebrew cask optional".
        assert "brew install --cask docker" in body

    def test_loads_launchdaemon(self):
        body = POSTINSTALL.read_text(encoding="utf-8")
        assert "launchctl bootstrap" in body
        assert "launchctl kickstart" in body


class TestUninstall:
    def test_removes_launchdaemon_and_binaries(self):
        body = UNINSTALL.read_text(encoding="utf-8")
        assert "launchctl bootout system/mn.sentry.agent" in body
        assert "rm -f \"$PLIST\"" in body
        assert "rm -rf /usr/local/sentry-agent" in body

    def test_preserves_config(self):
        body = UNINSTALL.read_text(encoding="utf-8")
        assert "rm -rf /etc/sentry-agent" not in body
        assert "preserved" in body.lower()


# ---------------------------------------------------------------------------
# Homebrew cask
# ---------------------------------------------------------------------------

class TestHomebrewCask:
    def test_cask_shape(self):
        body = CASK.read_text(encoding="utf-8")
        assert 'cask "sentry-agent" do' in body
        assert "depends_on cask: \"docker\"" in body
        assert "launchctl: \"mn.sentry.agent\"" in body
        assert "pkgutil:   \"mn.sentry.agent\"" in body


# ---------------------------------------------------------------------------
# GitHub Actions workflow
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


class TestMacosWorkflow:
    def test_exists(self):
        assert WORKFLOW.exists()

    def test_runs_on_macos_latest(self, workflow):
        for job_id in workflow["jobs"]:
            assert workflow["jobs"][job_id]["runs-on"] == "macos-latest"

    def test_triggers(self, workflow):
        triggers = workflow.get("on") or workflow.get(True)
        assert "agent-v*" in triggers["push"].get("tags", [])

    def test_validate_lints_shell_and_plist(self, workflow):
        steps = workflow["jobs"]["validate"]["steps"]
        names = [s.get("name", "") for s in steps]
        assert any("shellcheck" in n.lower() for n in names)
        assert any("plist" in n.lower() for n in names)

    def test_signing_is_secret_gated(self, workflow):
        """productsign + notarize steps must be secret-conditional so
        PR builds from forks stay green."""
        build_steps = workflow["jobs"]["build"]["steps"]
        sign_step = next(s for s in build_steps if s.get("name") == "Import signing cert")
        assert "MACOS_CERT_BASE64" in sign_step["if"]
        notary_step = next(s for s in build_steps if s.get("name") == "Notarize")
        assert "MACOS_NOTARY_KEY_ID" in notary_step["if"]

    def test_release_asset_on_tag(self, workflow):
        steps = workflow["jobs"]["build"]["steps"]
        release = next(s for s in steps if s.get("name") == "Attach to release")
        assert release["if"].startswith("startsWith(github.ref, 'refs/tags/agent-v')")

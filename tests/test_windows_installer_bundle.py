"""Static validation of the Windows installer bundle (T4-03).

We can't actually compile Inno Setup or run signtool in pytest — both
need Windows + external tooling — so these tests pin the *contract*
that the CI job depends on:

* Required Inno directives (UAC, 64-bit, version define, [Run] etc.)
* Docker Desktop detection logic exists in both the .iss Code section
  AND the bootstrap.ps1 so neither silently drifts from the DoD.
* PowerShell files parse with the stdlib-available `System.Management
  .Automation.Language.Parser` (via the `powershell` / `pwsh` binary).
* The GitHub Actions workflow has all the shape bits: triggers,
  ISCC call, signtool-guarded signing, artifact upload.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = ROOT / "agent" / "installer" / "windows"

ISS_PATH = INSTALLER_DIR / "SentryAgent.iss"
BOOTSTRAP_PS1 = INSTALLER_DIR / "bootstrap.ps1"
SERVICE_WRAPPER_PS1 = INSTALLER_DIR / "service-wrapper.ps1"
UNINSTALL_PS1 = INSTALLER_DIR / "uninstall.ps1"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "agent-installer-windows.yml"


# ---------------------------------------------------------------------------
# Inno Setup .iss
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def iss_text() -> str:
    return ISS_PATH.read_text(encoding="utf-8")


class TestInnoScript:
    def test_file_exists(self):
        assert ISS_PATH.exists(), "SentryAgent.iss must ship in the repo"

    @pytest.mark.parametrize("directive", [
        "AppName=Sentry Agent",
        "AppId=",
        "PrivilegesRequired=admin",
        "ArchitecturesAllowed=x64",
        "ArchitecturesInstallIn64BitMode=x64",
        "OutputBaseFilename=SentryAgentSetup",
        "DefaultDirName=",
        "MinVersion=",
        "WizardStyle=modern",
    ])
    def test_required_directive_present(self, iss_text, directive):
        """Each directive encodes a DoD line — removing any of them
        would drop the UAC prompt, 64-bit gate, or install target
        that customers depend on."""
        assert directive in iss_text, f"missing required directive: {directive}"

    def test_version_is_parameterized(self, iss_text):
        """CI compiles with /DSentryVersion=<semver>. The .iss must
        consume that define rather than hard-coding 0.0.0."""
        assert "#ifndef SentryVersion" in iss_text
        assert "AppVersion={#SentryVersion}" in iss_text

    @pytest.mark.parametrize("section", ["[Setup]", "[Files]", "[Run]", "[UninstallRun]", "[Code]"])
    def test_sections_present(self, iss_text, section):
        assert section in iss_text

    def test_bootstrap_invoked_via_powershell(self, iss_text):
        """[Run] must call powershell.exe with our bootstrap.ps1 —
        this is how Docker Desktop detect + install + agent image
        pull all happen."""
        assert "powershell.exe" in iss_text
        assert "bootstrap.ps1" in iss_text
        assert "-ExecutionPolicy Bypass" in iss_text
        assert "runhidden" in iss_text

    def test_uninstall_hook_present(self, iss_text):
        assert "uninstall.ps1" in iss_text
        assert "RunOnceId" in iss_text

    def test_docker_detection_in_code_section(self, iss_text):
        """Pascal routine must probe the registry for Docker Desktop."""
        assert "function DetectDockerDesktop" in iss_text
        assert "SOFTWARE\\Docker Inc.\\Docker Desktop" in iss_text

    def test_config_url_wizard_page(self, iss_text):
        """The wizard must collect the T4-02 signed URL so bootstrap
        can place config.yaml on first boot."""
        assert "CreateInputQueryPage" in iss_text
        assert "CONFIGURL" in iss_text  # accepted as CLI parameter too

    def test_programdata_acl_hardened(self, iss_text):
        """[Dirs] must restrict C:\\ProgramData\\Sentry\\Agent to
        Admins + SYSTEM — config.yaml carries the raw API key."""
        assert "{commonappdata}\\Sentry\\Agent" in iss_text
        assert "admins-full" in iss_text
        assert "system-full" in iss_text


# ---------------------------------------------------------------------------
# bootstrap.ps1 — content guards
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bootstrap_text() -> str:
    return BOOTSTRAP_PS1.read_text(encoding="utf-8")


class TestBootstrapScript:
    def test_file_exists(self):
        assert BOOTSTRAP_PS1.exists()

    def test_takes_mandatory_install_and_image_params(self, bootstrap_text):
        # Param block declarations must be there — without them the .iss
        # [Run] call would fail at runtime with PositionalParameterNotFound.
        assert "Mandatory = $true" in bootstrap_text
        assert "$InstallDir" in bootstrap_text
        assert "$Image" in bootstrap_text
        assert "$ConfigUrl" in bootstrap_text

    def test_detects_docker_desktop(self, bootstrap_text):
        assert "Test-DockerDesktopInstalled" in bootstrap_text
        assert "HKLM:\\SOFTWARE\\Docker Inc.\\Docker Desktop" in bootstrap_text

    def test_installs_docker_desktop_when_missing(self, bootstrap_text):
        assert "Install-DockerDesktop" in bootstrap_text
        assert "desktop.docker.com/win/main/amd64" in bootstrap_text
        assert "--quiet" in bootstrap_text
        assert "--accept-license" in bootstrap_text

    def test_waits_for_docker_engine(self, bootstrap_text):
        assert "Wait-DockerEngineReady" in bootstrap_text
        assert "docker info" in bootstrap_text

    def test_pulls_agent_image(self, bootstrap_text):
        assert "docker pull" in bootstrap_text

    def test_registers_scheduled_task(self, bootstrap_text):
        assert "Register-ScheduledTask" in bootstrap_text
        assert "-AtStartup" in bootstrap_text
        assert "SYSTEM" in bootstrap_text  # runs as SYSTEM, not a user

    def test_config_file_gets_hardened_acl(self, bootstrap_text):
        assert "SetAccessRuleProtection" in bootstrap_text
        assert "BUILTIN\\Administrators" in bootstrap_text
        assert "NT AUTHORITY\\SYSTEM" in bootstrap_text

    def test_has_transcript_logging(self, bootstrap_text):
        assert "Start-Transcript" in bootstrap_text
        assert "Stop-Transcript" in bootstrap_text


# ---------------------------------------------------------------------------
# PowerShell parser — semantic syntax validation
# ---------------------------------------------------------------------------

def _find_powershell() -> str | None:
    for name in ("pwsh", "powershell"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


@pytest.mark.parametrize("ps_path", [BOOTSTRAP_PS1, SERVICE_WRAPPER_PS1, UNINSTALL_PS1])
def test_powershell_script_parses(tmp_path, ps_path):
    """Run the PowerShell Parser over each script. This catches
    typos + unclosed braces that would otherwise only surface at
    Task-Scheduler-runtime on a customer's machine.

    We send the parser harness via -File (not -Command) because
    multi-line commands on Windows PowerShell 5.1 break on newlines.
    """
    ps = _find_powershell()
    if ps is None:
        pytest.skip("PowerShell binary not available on this runner")

    harness = tmp_path / "parse-check.ps1"
    harness.write_text(
        textwrap.dedent(
            f"""
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile(
                '{ps_path.as_posix()}', [ref]$null, [ref]$errors
            ) | Out-Null
            if ($errors -and $errors.Count -gt 0) {{
                $errors | ForEach-Object {{ Write-Host $_.Message }}
                exit 1
            }}
            exit 0
            """
        ).strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"PowerShell parser errors in {ps_path.name}:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# GitHub Actions workflow shape
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


class TestWindowsInstallerWorkflow:
    def test_workflow_file_exists(self):
        assert WORKFLOW_PATH.exists()

    def test_triggers_cover_main_tag_and_pr(self, workflow):
        # YAML `on:` parses to the key `True` due to the `on` ↔ bool
        # conflict — try both forms so the test survives either PyYAML
        # behavior.
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        assert "push" in triggers
        assert "pull_request" in triggers
        assert "workflow_dispatch" in triggers
        assert "agent-v*" in triggers["push"].get("tags", [])

    def test_build_job_runs_on_windows(self, workflow):
        build = workflow["jobs"]["build"]
        assert build["runs-on"] == "windows-latest"

    def test_build_steps_include_iscc_and_artifact_upload(self, workflow):
        steps = workflow["jobs"]["build"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert any("Inno Setup" in n for n in step_names), step_names
        assert any("Compile" in n for n in step_names), step_names
        assert any("Upload" in n for n in step_names), step_names

    def test_signing_is_guarded_by_secret_presence(self, workflow):
        """Authenticode signing must be conditional on the cert
        secret being configured — PR builds from forks would otherwise
        fail hard trying to pull a secret that isn't set."""
        steps = workflow["jobs"]["build"]["steps"]
        sign_step = next(s for s in steps if s.get("name") == "Authenticode sign")
        assert sign_step["if"].startswith(
            "steps.sign_decision.outputs.sign == 'true'"
        ) or "sign_decision" in sign_step["if"]
        # The decision step itself must check secrets.WINDOWS_CERT_BASE64
        decision = next(s for s in steps if s.get("id") == "sign_decision")
        assert "WINDOWS_CERT_BASE64" in str(decision)

    def test_release_asset_upload_on_tag(self, workflow):
        """Tags must publish the installer as a GitHub release asset
        so the customer portal can link to a stable URL."""
        steps = workflow["jobs"]["build"]["steps"]
        release = next(
            s for s in steps if s.get("name") == "Attach installer to release"
        )
        assert release["if"].startswith("startsWith(github.ref, 'refs/tags/agent-v')")

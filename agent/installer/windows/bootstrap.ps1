<#
.SYNOPSIS
    Sentry Agent Windows bootstrap -- runs once from the Inno Setup
    installer's [Run] section under elevated rights.

.DESCRIPTION
    1. Verify Docker Desktop is installed; download and silently
       install it if missing.
    2. Wait for the Docker engine to become responsive.
    3. Download the per-tenant config.yaml from a 24-hour signed URL
       (T4-02) and place it in ProgramData.
    4. docker pull the agent image from GHCR.
    5. Register (or update) the `SentryAgent` scheduled task that
       runs service-wrapper.ps1 at system startup.

.NOTES
    Designed to be idempotent -- rerunning it on an already-configured
    host should be a no-op beyond refreshing the image pull.
#>

param(
    [Parameter(Mandatory = $true)]
    [string] $InstallDir,

    [Parameter(Mandatory = $true)]
    [string] $Image,

    [string] $ConfigUrl = ''
)

$ErrorActionPreference = 'Stop'

$LogDir = Join-Path $env:ProgramData 'Sentry\Agent\logs'
$ConfigDir = Join-Path $env:ProgramData 'Sentry\Agent'
$ConfigPath = Join-Path $ConfigDir 'config.yaml'
$DockerInstallerUrl = 'https://desktop.docker.com/win/main/amd64/Docker Desktop Installer.exe'
$TaskName = 'SentryAgent'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

$LogFile = Join-Path $LogDir ('bootstrap-{0:yyyyMMdd-HHmmss}.log' -f (Get-Date))
Start-Transcript -Path $LogFile -Force | Out-Null

function Write-Step {
    param([string] $Message)
    Write-Host ("[sentry-bootstrap] {0}" -f $Message)
}

function Test-DockerDesktopInstalled {
    # Registry is authoritative post-4.x; filesystem check backstops
    # older installs that lacked the reg entry.
    if (Test-Path 'HKLM:\SOFTWARE\Docker Inc.\Docker Desktop') {
        return $true
    }
    $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    return (Test-Path $exe)
}

function Install-DockerDesktop {
    Write-Step 'Docker Desktop not detected -- downloading installer...'
    $tmp = Join-Path $env:TEMP 'DockerDesktopInstaller.exe'
    # Use BITS when available (resumable, integrates with Group Policy);
    # fall back to Invoke-WebRequest on stripped images.
    try {
        Start-BitsTransfer -Source $DockerInstallerUrl -Destination $tmp -ErrorAction Stop
    }
    catch {
        Write-Step "BITS unavailable ($($_.Exception.Message)); retrying with Invoke-WebRequest"
        Invoke-WebRequest -Uri $DockerInstallerUrl -OutFile $tmp -UseBasicParsing
    }

    Write-Step 'Running Docker Desktop installer silently...'
    # --quiet suppresses the UI; --accept-license auto-accepts Docker's EULA
    # (the customer accepted ours already in the wizard).
    $proc = Start-Process -FilePath $tmp -ArgumentList 'install', '--quiet', '--accept-license' `
        -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Docker Desktop installer exited with code $($proc.ExitCode)"
    }
    Write-Step 'Docker Desktop installed.'
}

function Wait-DockerEngineReady {
    param([int] $TimeoutSeconds = 300)
    Write-Step "Waiting up to ${TimeoutSeconds}s for Docker engine..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            & docker info --format '{{.ServerVersion}}' *>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Step 'Docker engine is ready.'
                return
            }
        }
        catch {
            # swallow -- engine not up yet
        }
        Start-Sleep -Seconds 5
    }
    throw "Docker engine did not become ready within ${TimeoutSeconds} seconds."
}

function Download-Config {
    param([string] $Url)
    if (-not $Url) {
        Write-Step 'No /CONFIGURL supplied -- leaving config.yaml for later manual setup.'
        return
    }
    Write-Step "Fetching config.yaml from $Url"
    # UseBasicParsing -> no IE dependency; -Headers empty because the URL
    # itself is the credential (HMAC-signed per T4-02).
    Invoke-WebRequest -Uri $Url -OutFile $ConfigPath -UseBasicParsing
    # Tighten ACL -- config.yaml holds the raw API key; only Admins +
    # SYSTEM should be able to read it.
    $acl = Get-Acl $ConfigPath
    $acl.SetAccessRuleProtection($true, $false)   # disable inheritance
    $acl.Access | ForEach-Object { $acl.RemoveAccessRule($_) | Out-Null }
    foreach ($principal in 'BUILTIN\Administrators', 'NT AUTHORITY\SYSTEM') {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $principal, 'FullControl', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -Path $ConfigPath -AclObject $acl
    Write-Step 'config.yaml written with Admin-only ACL.'
}

function Pull-AgentImage {
    param([string] $Ref)
    Write-Step "docker pull $Ref"
    & docker pull $Ref
    if ($LASTEXITCODE -ne 0) {
        throw "docker pull $Ref failed (exit $LASTEXITCODE)."
    }
}

function Register-AgentTask {
    param([string] $Wrapper, [string] $Ref)
    # Remove the existing task first so we never leave an orphaned
    # definition pointing at a previous InstallDir.
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $args = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-WindowStyle', 'Hidden',
        '-File', "`"$Wrapper`"",
        '-Image', "`"$Ref`""
    )
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ($args -join ' ')
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    # RestartInterval keeps the task flapping-resistant -- a crashing
    # container will be relaunched by Task Scheduler every minute.
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -RestartCount 999

    Register-ScheduledTask -TaskName $TaskName `
        -Description 'Sentry edge agent (Docker-based RTSP bridge)' `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null

    Write-Step "Scheduled task '$TaskName' registered."
    Start-ScheduledTask -TaskName $TaskName
    Write-Step "Scheduled task '$TaskName' started."
}

# ------- main -------

try {
    if (-not (Test-DockerDesktopInstalled)) {
        Install-DockerDesktop
    }
    else {
        Write-Step 'Docker Desktop already installed.'
    }

    Wait-DockerEngineReady

    Download-Config -Url $ConfigUrl

    Pull-AgentImage -Ref $Image

    $wrapper = Join-Path $InstallDir 'service-wrapper.ps1'
    Register-AgentTask -Wrapper $wrapper -Ref $Image

    Write-Step 'Sentry Agent bootstrap complete.'
    exit 0
}
catch {
    Write-Host "[sentry-bootstrap] FATAL: $($_.Exception.Message)"
    Write-Host $_.ScriptStackTrace
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}

<#
.SYNOPSIS
    Foreground runner invoked by the SentryAgent scheduled task.

.DESCRIPTION
    Keeps a single `docker run` process in the foreground so Windows
    Task Scheduler's own restart policy handles container crashes.
    We do NOT use `-d` -- if the container detaches, Task Scheduler
    thinks the task finished and won't restart it.
#>

param(
    [Parameter(Mandatory = $true)]
    [string] $Image
)

$ErrorActionPreference = 'Stop'
$ContainerName = 'sentry-agent'
$ConfigPath = Join-Path $env:ProgramData 'Sentry\Agent\config.yaml'
$LogDir = Join-Path $env:ProgramData 'Sentry\Agent\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir ('agent-{0:yyyyMMdd}.log' -f (Get-Date))
Start-Transcript -Path $LogFile -Append | Out-Null

try {
    # Ensure any stale container from a crashed previous run is gone --
    # `docker run --name` fails if a dead container still occupies
    # the name.
    & docker rm -f $ContainerName *>$null

    if (-not (Test-Path $ConfigPath)) {
        Write-Host "[sentry-agent] config.yaml missing at $ConfigPath -- bootstrap not complete."
        Start-Sleep -Seconds 60
        exit 2
    }

    # --init reaps zombies inside the container. --restart is NOT
    # set because the Task Scheduler owns restart. We mount the
    # config read-only. Note: PowerShell's `${var}:` syntax collides
    # with scoped-variable parsing, so build the -v argument via
    # string concatenation.
    $volumeSpec = $ConfigPath + ':/etc/sentry-agent/config.yaml:ro'
    $dockerArgs = @(
        'run',
        '--name', $ContainerName,
        '--init',
        '--pull', 'always',
        '-v', $volumeSpec,
        $Image
    )

    & docker @dockerArgs
    exit $LASTEXITCODE
}
finally {
    Stop-Transcript | Out-Null
}

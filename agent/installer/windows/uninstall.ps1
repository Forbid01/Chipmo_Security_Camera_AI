<#
.SYNOPSIS
    Sentry Agent Windows uninstall hook -- called from
    [UninstallRun] in SentryAgent.iss.

.DESCRIPTION
    Stops + removes the scheduled task, tears down the container,
    and prunes the pulled image. ProgramData config is intentionally
    preserved so reinstalls keep the tenant's API key -- wiping it
    requires manual deletion of C:\ProgramData\Sentry\Agent.
#>

param(
    [Parameter(Mandatory = $true)]
    [string] $Image
)

$TaskName = 'SentryAgent'
$ContainerName = 'sentry-agent'
$LogDir = Join-Path $env:ProgramData 'Sentry\Agent\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir ('uninstall-{0:yyyyMMdd-HHmmss}.log' -f (Get-Date))
Start-Transcript -Path $LogFile -Force | Out-Null

function Remove-Task {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Write-Host "[sentry-uninstall] Stopping scheduled task $TaskName"
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
}

function Remove-Container {
    # Non-fatal -- a healthy uninstall can tolerate a missing
    # container (e.g. Docker was already uninstalled).
    & docker rm -f $ContainerName *>$null
}

function Remove-Image {
    param([string] $Ref)
    & docker image rm $Ref *>$null
}

try {
    Remove-Task
    Remove-Container
    Remove-Image -Ref $Image
    Write-Host '[sentry-uninstall] Complete.'
    exit 0
}
catch {
    Write-Host "[sentry-uninstall] Non-fatal error: $($_.Exception.Message)"
    exit 0
}
finally {
    Stop-Transcript | Out-Null
}

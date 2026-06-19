param(
    [Parameter(Mandatory = $true)][string]$Service,
    [switch]$StepA,
    [switch]$StepB,
    [switch]$StepC,
    [switch]$RollbackA,
    [switch]$RollbackB,
    [switch]$RollbackC,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Container = if ($Service.StartsWith("ronki-")) { $Service } else { "ronki-$Service" }

function Complete-Step {
    param([string]$Name, [string]$Message)
    if ($DryRun) {
        Write-Output "[DRY-RUN] $Name`: would $Message for $Container"
        exit 0
    }
    Write-Output "[multi_step_deploy] $Name`: $Message for $Container"
}

if ($StepA) {
    Complete-Step "step-A" "drain traffic"
    docker stop $Container 2>$null | Out-Null
    exit 0
}
if ($StepB) {
    Complete-Step "step-B" "apply config and restart"
    docker start $Container 2>$null | Out-Null
    docker restart $Container | Out-Null
    exit $LASTEXITCODE
}
if ($StepC) {
    Complete-Step "step-C" "re-enable traffic"
    docker start $Container 2>$null | Out-Null
    Start-Sleep -Seconds 2
    $status = docker inspect --format '{{.State.Status}}' $Container 2>$null
    if ($status -eq "running") { exit 0 }
    Write-Output "[multi_step_deploy] ERROR: $Container status=$status"
    exit 1
}
if ($RollbackC) {
    Complete-Step "rollback-C" "disable traffic"
    docker stop $Container 2>$null | Out-Null
    exit 0
}
if ($RollbackB) {
    Complete-Step "rollback-B" "revert config"
    docker restart $Container | Out-Null
    exit $LASTEXITCODE
}
if ($RollbackA) {
    Complete-Step "rollback-A" "restore traffic"
    docker start $Container 2>$null | Out-Null
    exit 0
}

if ($DryRun) {
    Write-Output "[DRY-RUN] would execute: full multi-step deploy on $Container"
    exit 0
}

Write-Output "[multi_step_deploy] ERROR: choose one of -StepA/-StepB/-StepC/-RollbackA/-RollbackB/-RollbackC"
exit 1

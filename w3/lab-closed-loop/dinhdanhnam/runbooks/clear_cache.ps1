param(
    [Parameter(Mandatory = $true)][string]$Service,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Container = if ($Service.StartsWith("ronki-")) { $Service } else { "ronki-$Service" }

if ($DryRun) {
    Write-Output "[DRY-RUN] would execute: docker kill --signal=SIGHUP $Container"
    exit 0
}

docker inspect $Container *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Output "[clear_cache] ERROR: container $Container not found."
    exit 1
}

Write-Output "[clear_cache] Sending SIGHUP to $Container..."
docker kill --signal=SIGHUP $Container | Out-Null
Write-Output "[clear_cache] SIGHUP sent to $Container."
exit 0

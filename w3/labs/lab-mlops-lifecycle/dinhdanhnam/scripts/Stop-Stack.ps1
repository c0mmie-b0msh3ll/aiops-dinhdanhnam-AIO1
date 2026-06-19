param(
    [switch]$RemoveVolumes
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ComposeFile = Join-Path $Root "data-pack\configs\docker-compose.yml"
$Project = "mlops"

Write-Output "[Stop-Stack] Stopping MLOps stack..."
if ($RemoveVolumes) {
    docker compose -p $Project -f $ComposeFile down --volumes --remove-orphans
} else {
    docker compose -p $Project -f $ComposeFile down --remove-orphans
}
exit $LASTEXITCODE

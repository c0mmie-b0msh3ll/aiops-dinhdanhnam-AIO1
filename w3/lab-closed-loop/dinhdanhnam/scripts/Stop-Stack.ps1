param(
    [switch]$KeepVolumes
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ComposeFile = Join-Path $Root "data-pack\configs\docker-compose.yml"
$Project = "ronki"

Write-Output "[Stop-Stack] Stopping Ronki stack..."
if ($KeepVolumes) {
    docker compose -p $Project -f $ComposeFile down --remove-orphans
} else {
    docker compose -p $Project -f $ComposeFile down --volumes --remove-orphans
}
exit $LASTEXITCODE

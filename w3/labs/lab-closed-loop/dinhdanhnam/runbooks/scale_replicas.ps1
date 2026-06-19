param(
    [Parameter(Mandatory = $true)][string]$Service,
    [int]$Replicas = 2,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeFile = Resolve-Path (Join-Path $ScriptDir "..\..\data-pack\configs\docker-compose.yml")
$Project = "ronki"

if ($DryRun) {
    Write-Output "[DRY-RUN] would execute: docker compose -p $Project -f $ComposeFile up -d --scale $Service=$Replicas --no-recreate"
    exit 0
}

Write-Output "[scale_replicas] Scaling $Service to $Replicas replicas..."
docker compose -p $Project -f $ComposeFile up -d --scale "$Service=$Replicas" --no-recreate
exit $LASTEXITCODE

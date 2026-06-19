param(
    [Parameter(Mandatory = $true)][string]$Service,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeFile = Resolve-Path (Join-Path $ScriptDir "..\..\data-pack\configs\docker-compose.yml")
$Project = "ronki"
$Container = if ($Service.StartsWith("ronki-")) { $Service } else { "ronki-$Service" }
$ComposeService = $Container -replace "^ronki-", ""
$ManagedServices = @("frontend", "api-gateway", "payment-svc", "inventory-svc", "checkout-svc")
$Ports = @{
    "frontend" = 8080
    "api-gateway" = 8081
    "payment-svc" = 8082
    "inventory-svc" = 8083
    "checkout-svc" = 8084
}

function Wait-ServiceHealth {
    param([string]$Name, [int]$TimeoutSeconds = 90)
    if (-not $Ports.ContainsKey($Name)) { return $true }
    $url = "http://localhost:$($Ports[$Name])/health"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5 | Out-Null
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Get-FaultLabel {
    param([string]$Name)
    $raw = docker inspect $Name 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return "" }
    $info = $raw | ConvertFrom-Json
    if ($info[0].Config.Labels.PSObject.Properties.Name -contains "ronki.injected") {
        return $info[0].Config.Labels."ronki.injected"
    }
    return ""
}

if ($DryRun) {
    Write-Output "[DRY-RUN] would execute: restore or restart $Container"
    exit 0
}

Write-Output "[restart_service] Handling $Container..."
$isManaged = $ManagedServices -contains $ComposeService
if ($isManaged) {
    Write-Output "[restart_service] Recreating compose service $ComposeService to restore known-good config..."
    docker rm -f $Container 2>$null | Out-Null
    docker compose -p $Project -f $ComposeFile up -d $ComposeService
    Start-Sleep -Seconds 5
    $status = docker inspect --format '{{.State.Status}}' $Container 2>$null
    if ($status -eq "running") {
        if (-not (Wait-ServiceHealth -Name $ComposeService -TimeoutSeconds 90)) {
            Write-Output "[restart_service] ERROR: $Container is running but /health did not become ready."
            exit 1
        }
        Write-Output "[restart_service] $Container is running."
        exit 0
    }
    Write-Output "[restart_service] ERROR: $Container status=$status after recreate."
    exit 1
}

$fault = Get-FaultLabel -Name $Container

if ($fault) {
    Write-Output "[restart_service] $Container has injected fault '$fault'; restoring compose service $ComposeService..."
    docker rm -f $Container | Out-Null
    docker compose -p $Project -f $ComposeFile up -d $ComposeService
} else {
$exists = docker inspect $Container 2>$null
if ($LASTEXITCODE -ne 0 -or -not $exists) {
        Write-Output "[restart_service] Container $Container not found; starting compose service $ComposeService..."
        docker compose -p $Project -f $ComposeFile up -d $ComposeService
    } else {
        docker restart $Container | Out-Null
    }
}

Start-Sleep -Seconds 5
$status = docker inspect --format '{{.State.Status}}' $Container 2>$null
if ($status -eq "running") {
    if (-not (Wait-ServiceHealth -Name $ComposeService -TimeoutSeconds 90)) {
        Write-Output "[restart_service] ERROR: $Container is running but /health did not become ready."
        exit 1
    }
    Write-Output "[restart_service] $Container is running."
    exit 0
}

Write-Output "[restart_service] ERROR: $Container status=$status after restart."
exit 1

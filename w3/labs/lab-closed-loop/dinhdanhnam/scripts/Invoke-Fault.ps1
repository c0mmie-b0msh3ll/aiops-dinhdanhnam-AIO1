param(
    [Parameter(Mandatory = $true)][string]$Fault,
    [Parameter(Mandatory = $false)][string]$Container,
    [Parameter(Mandatory = $false)][string]$Param = "500ms"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ComposeFile = Join-Path $Root "data-pack\configs\docker-compose.yml"
$ServicePy = Resolve-Path (Join-Path $Root "data-pack\configs\services\service.py")
$Project = "ronki"

$ports = @{
    "frontend" = 8080
    "api-gateway" = 8081
    "payment-svc" = 8082
    "inventory-svc" = 8083
    "checkout-svc" = 8084
}
$baseLatency = @{
    "frontend" = "50"
    "api-gateway" = "80"
    "payment-svc" = "120"
    "inventory-svc" = "40"
    "checkout-svc" = "150"
}
$jitter = @{
    "frontend" = "10"
    "api-gateway" = "15"
    "payment-svc" = "20"
    "inventory-svc" = "8"
    "checkout-svc" = "25"
}
$failRate = @{
    "frontend" = "0.01"
    "api-gateway" = "0.01"
    "payment-svc" = "0.02"
    "inventory-svc" = "0.01"
    "checkout-svc" = "0.015"
}

function Resolve-Names {
    param([string]$Name)
    $containerName = if ($Name.StartsWith("ronki-")) { $Name } else { "ronki-$Name" }
    $serviceName = $containerName -replace "^ronki-", ""
    return @{ Container = $containerName; Service = $serviceName }
}

function Get-NetworkName {
    $name = docker network ls --format "{{.Name}}" | Select-String -Pattern "^${Project}_ronki$" | Select-Object -First 1
    if ($name) { return $name.ToString() }
    $fallback = docker network ls --format "{{.Name}}" | Select-String -Pattern "ronki" | Select-Object -First 1
    if ($fallback) { return $fallback.ToString() }
    return "${Project}_ronki"
}

function Restore-Service {
    param([string]$Service, [string]$ContainerName)
    Write-Output "[Invoke-Fault] Restoring $Service from Compose..."
    docker rm -f $ContainerName 2>$null | Out-Null
    docker compose -p $Project -f $ComposeFile up -d $Service
}

if ($Fault -eq "--concurrent") {
    if (-not $Container -or -not $Param) {
        Write-Output "Usage: .\Invoke-Fault.ps1 --concurrent <service1> <service2>"
        exit 1
    }
    $script = $MyInvocation.MyCommand.Path
    $j1 = Start-Job -ScriptBlock { param($s, $svc) powershell -NoProfile -ExecutionPolicy Bypass -File $s latency $svc 500ms } -ArgumentList $script, $Container
    $j2 = Start-Job -ScriptBlock { param($s, $svc) powershell -NoProfile -ExecutionPolicy Bypass -File $s latency $svc 500ms } -ArgumentList $script, $Param
    Receive-Job -Job $j1, $j2 -Wait -AutoRemoveJob
    exit 0
}

if (-not $Container) {
    Write-Output "Usage: .\Invoke-Fault.ps1 <latency|error|kill|pause|resume|recover|clear-latency> <service-or-container> [param]"
    exit 1
}

$names = Resolve-Names -Name $Container
$ContainerName = $names.Container
$Service = $names.Service

switch ($Fault) {
    "latency" {
        if (-not $ports.ContainsKey($Service)) { throw "Unknown service '$Service'" }
        $delayMs = [int](($Param -replace "ms", "") -replace "[^0-9]", "")
        if ($delayMs -le 0) { $delayMs = 500 }
        $network = Get-NetworkName
        Write-Output "[Invoke-Fault] Replacing $ContainerName with slow latency container (${delayMs}ms base)..."
        docker rm -f $ContainerName 2>$null | Out-Null
        $args = @(
            "run", "-d",
            "--name", $ContainerName,
            "--network", $network,
            "--network-alias", $Service,
            "-p", "$($ports[$Service]):8080",
            "--label", "ronki.injected=latency",
            "-e", "SERVICE_NAME=$Service",
            "-e", "BASE_LATENCY_MS=$delayMs",
            "-e", "JITTER_MS=25",
            "-e", "FAIL_RATE=$($failRate[$Service])",
            "-v", "${ServicePy}:/app/service.py:ro",
            "-w", "/app",
            "python:3.12-slim",
            "sh", "-c", "pip install --quiet fastapi uvicorn prometheus-client && uvicorn service:app --host 0.0.0.0 --port 8080"
        )
        & docker @args
    }
    "error" {
        if (-not $ports.ContainsKey($Service)) { throw "Unknown service '$Service'" }
        $network = Get-NetworkName
        Write-Output "[Invoke-Fault] Replacing $ContainerName with high-error container..."
        docker rm -f $ContainerName 2>$null | Out-Null
        $args = @(
            "run", "-d",
            "--name", $ContainerName,
            "--network", $network,
            "--network-alias", $Service,
            "-p", "$($ports[$Service]):8080",
            "--label", "ronki.injected=error",
            "-e", "SERVICE_NAME=$Service",
            "-e", "BASE_LATENCY_MS=$($baseLatency[$Service])",
            "-e", "JITTER_MS=$($jitter[$Service])",
            "-e", "FAIL_RATE=0.50",
            "-v", "${ServicePy}:/app/service.py:ro",
            "-w", "/app",
            "python:3.12-slim",
            "sh", "-c", "pip install --quiet fastapi uvicorn prometheus-client && uvicorn service:app --host 0.0.0.0 --port 8080"
        )
        & docker @args
    }
    "kill" {
        Write-Output "[Invoke-Fault] Stopping $ContainerName..."
        docker stop $ContainerName
    }
    "pause" {
        Write-Output "[Invoke-Fault] Pausing $ContainerName..."
        docker pause $ContainerName
    }
    "resume" {
        Write-Output "[Invoke-Fault] Resuming $ContainerName..."
        docker unpause $ContainerName
    }
    "recover" {
        Restore-Service -Service $Service -ContainerName $ContainerName
    }
    "clear-latency" {
        Restore-Service -Service $Service -ContainerName $ContainerName
    }
    default {
        Write-Output "Unknown fault '$Fault'. Valid: latency, error, kill, pause, resume, recover, clear-latency, --concurrent"
        exit 1
    }
}

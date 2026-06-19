param(
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ComposeFile = Join-Path $Root "data-pack\configs\docker-compose.yml"
$Project = "ronki"

Write-Output "[Start-Stack] Starting Ronki stack with Docker Compose..."
docker compose -p $Project -f $ComposeFile up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "[Start-Stack] Waiting $WaitSeconds seconds for services..."
Start-Sleep -Seconds $WaitSeconds

$checks = @(
    @{ Name = "frontend"; Url = "http://localhost:8080/health" },
    @{ Name = "api-gateway"; Url = "http://localhost:8081/health" },
    @{ Name = "payment-svc"; Url = "http://localhost:8082/health" },
    @{ Name = "inventory-svc"; Url = "http://localhost:8083/health" },
    @{ Name = "checkout-svc"; Url = "http://localhost:8084/health" },
    @{ Name = "prometheus"; Url = "http://localhost:9090/-/healthy" },
    @{ Name = "alertmanager"; Url = "http://localhost:9093/-/healthy" }
)

$allOk = $true
foreach ($check in $checks) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $check.Url -TimeoutSec 5 | Out-Null
        Write-Output ("  [OK]   {0} - {1}" -f $check.Name, $check.Url)
    } catch {
        $allOk = $false
        Write-Output ("  [FAIL] {0} - {1}" -f $check.Name, $check.Url)
    }
}

Write-Output ""
Write-Output "Prometheus   : http://localhost:9090"
Write-Output "Alertmanager : http://localhost:9093"
Write-Output "Grafana      : http://localhost:3000"
if (-not $allOk) {
    Write-Output "Some services are still warming up. Re-run this script or wait 15 seconds."
}

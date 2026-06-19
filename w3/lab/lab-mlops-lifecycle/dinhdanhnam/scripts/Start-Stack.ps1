param(
    [int]$MlflowPort = 5050,
    [int]$MaxWaitSeconds = 120
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ComposeFile = Join-Path $Root "data-pack\configs\docker-compose.yml"
$Project = "mlops"

Write-Output "[Start-Stack] Starting MLOps stack..."
$env:MLFLOW_PORT = "$MlflowPort"
docker compose -p $Project -f $ComposeFile up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "[Start-Stack] Waiting for MLflow at http://localhost:$MlflowPort/health ..."
$deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
while ((Get-Date) -lt $deadline) {
    try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$MlflowPort/health" -TimeoutSec 5 | Out-Null
            Write-Output "[Start-Stack] MLflow is ready."
        Write-Output "MLflow      : http://localhost:$MlflowPort"
        Write-Output "Prometheus  : http://localhost:9090"
        Write-Output "Pushgateway : http://localhost:9091"
        Write-Output "Grafana     : http://localhost:3000"
        Write-Output "PowerShell env: `$env:MLFLOW_TRACKING_URI=`"http://localhost:$MlflowPort`""
        exit 0
    } catch {
        Start-Sleep -Seconds 3
    }
}

Write-Output "[Start-Stack] ERROR: MLflow did not become ready within $MaxWaitSeconds seconds."
docker compose -p $Project -f $ComposeFile logs mlflow
exit 1

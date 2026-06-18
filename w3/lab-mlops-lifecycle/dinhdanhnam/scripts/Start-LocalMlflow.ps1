param(
    [int]$Port = 5050
)

$ErrorActionPreference = "Stop"
$Submission = Resolve-Path (Join-Path $PSScriptRoot "..")
$Store = Join-Path $Submission "outputs\mlflow-local"
$Artifacts = Join-Path $Submission "outputs\mlflow-artifacts"
New-Item -ItemType Directory -Force $Store, $Artifacts | Out-Null
$ArtifactUri = "file:///" + (($Artifacts -replace "\\", "/") -replace " ", "%20")
$env:PYTHONIOENCODING = "utf-8"

Write-Output "[Start-LocalMlflow] Starting local MLflow on http://localhost:$Port"
Write-Output "[Start-LocalMlflow] Backend store: $Store\mlflow.db"
Write-Output "[Start-LocalMlflow] Artifacts    : $ArtifactUri"

python -m mlflow server `
    --backend-store-uri "sqlite:///$Store/mlflow.db" `
    --default-artifact-root "$ArtifactUri" `
    --host 127.0.0.1 `
    --port $Port

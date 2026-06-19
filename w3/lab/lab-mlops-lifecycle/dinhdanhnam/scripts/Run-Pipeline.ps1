param(
    [string]$MlflowUri = "http://localhost:5050",
    [switch]$AutoApprove,
    [switch]$SkipServe
)

$ErrorActionPreference = "Stop"
$Submission = Resolve-Path (Join-Path $PSScriptRoot "..")
$Data = Resolve-Path (Join-Path $Submission "..\data-pack\data")
$env:MLFLOW_TRACKING_URI = $MlflowUri
$env:PYTHONIOENCODING = "utf-8"
$env:AIOPS_EXPERIMENT_NAME = "anomaly-detection-windows"

Set-Location $Submission

Write-Output "[Run-Pipeline] Training v1 and registering @production..."
python pipeline.py --data (Join-Path $Data "baseline.csv")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipServe) {
    Write-Output "[Run-Pipeline] Starting serve.py in a background PowerShell job..."
    $serveJob = Start-Job -ScriptBlock {
        param($dir)
        Set-Location $dir
        $env:MLFLOW_TRACKING_URI = $using:MlflowUri
        $env:PYTHONIOENCODING = "utf-8"
        $env:AIOPS_EXPERIMENT_NAME = "anomaly-detection-windows"
        python serve.py --host 0.0.0.0 --port 8000
    } -ArgumentList $Submission

    Write-Output "[Run-Pipeline] Waiting for serve.py..."
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/health/active-version" -TimeoutSec 5 | Out-Null
            Write-Output "[Run-Pipeline] serve.py is ready at http://localhost:8000"
            break
        } catch {
            Start-Sleep -Seconds 2
        }
    }
}

Write-Output "[Run-Pipeline] Running combined drift + performance check..."
python drift_detector.py `
    --reference (Join-Path $Data "baseline.csv") `
    --current (Join-Path $Data "drifted.csv") `
    --threshold 0.15 `
    --check-mode combined `
    --labeled-current (Join-Path $Data "drifted.csv") `
    --model-uri "models:/anomaly-detector@production"
if ($LASTEXITCODE -ne 0) {
    Write-Output "[Run-Pipeline] drift_detector exited non-zero because drift was detected. Continuing to retrain."
}

$args = @(
    "retrain.py",
    "--reference", (Join-Path $Data "baseline.csv"),
    "--current", (Join-Path $Data "drifted.csv"),
    "--holdout", (Join-Path $Data "holdout.csv"),
    "--post-deploy-eval", (Join-Path $Data "post_deploy_eval.csv")
)
if ($AutoApprove) { $args += "--auto-approve" }

Write-Output "[Run-Pipeline] Running retrain pipeline..."
python @args
exit $LASTEXITCODE

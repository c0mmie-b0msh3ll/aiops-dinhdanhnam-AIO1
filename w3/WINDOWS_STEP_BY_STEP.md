# Windows Step-by-Step Guide for the Two W3 Labs

This guide is written for PowerShell on Windows. Run commands from the repo root:

```powershell
cd D:\Study\Home_work\xBrain\aiops-dinhdanhnam-AIO1
```

## Lab 1: Closed-Loop Auto-Remediation

### What this lab is about

The closed-loop lab is the incident automation flow:

```text
Alertmanager alert -> decide runbook -> dry-run -> execute -> verify in Prometheus -> rollback if verify fails
```

The important file to read first is:

```text
w3/labs/lab-closed-loop/dinhdanhnam/closed_loop.py
```

The main logic is:

| Code area | What it does |
|---|---|
| `fetch_active_alerts` | Polls Alertmanager every 15 seconds. |
| `process_alert` | Handles one alert end-to-end. |
| `validate_runbook` | Rejects invalid/hallucinated runbook paths before any subprocess runs. |
| `BlastRadiusGuard` | Limits automation to 3 actions/minute and 5 restarts/service/hour. |
| `CircuitBreaker` | Halts automation after 3 consecutive failures. |
| `verify_service` | Queries Prometheus until p99 latency and `up` are healthy. |

### Windows scripts added

Bash scripts were replaced/wrapped with PowerShell scripts:

```text
w3/labs/lab-closed-loop/dinhdanhnam/scripts/Start-Stack.ps1
w3/labs/lab-closed-loop/dinhdanhnam/scripts/Stop-Stack.ps1
w3/labs/lab-closed-loop/dinhdanhnam/scripts/Invoke-Fault.ps1
w3/labs/lab-closed-loop/dinhdanhnam/scripts/Invoke-Traffic.ps1

w3/labs/lab-closed-loop/dinhdanhnam/runbooks/restart_service.ps1
w3/labs/lab-closed-loop/dinhdanhnam/runbooks/clear_cache.ps1
w3/labs/lab-closed-loop/dinhdanhnam/runbooks/scale_replicas.ps1
w3/labs/lab-closed-loop/dinhdanhnam/runbooks/multi_step_deploy.ps1
```

`closed_loop.py` now detects `.ps1` runbooks and calls PowerShell with:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File <runbook.ps1>
```

### Step 1: Install Python deps

```powershell
python -m pip install -r w3/labs/lab-closed-loop/dinhdanhnam/requirements.txt
```

### Step 2: Start the stack

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-closed-loop/dinhdanhnam/scripts/Start-Stack.ps1
```

Expected URLs:

```text
Prometheus   http://localhost:9090
Alertmanager http://localhost:9093
Grafana      http://localhost:3000
```

### Step 3: Test traffic and fault manually

Generate normal traffic:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-closed-loop/dinhdanhnam/scripts/Invoke-Traffic.ps1 -Service payment-svc -DurationSeconds 30
```

Inject Windows-compatible latency:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-closed-loop/dinhdanhnam/scripts/Invoke-Fault.ps1 latency payment-svc 900ms
```

This does not use Linux `tc/nsenter`. Instead, it replaces the container with a slow container using the same service name, port, and Docker network alias. That makes Prometheus and Alertmanager see the same kind of latency symptom.

Restore the service:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-closed-loop/dinhdanhnam/runbooks/restart_service.ps1 -Service payment-svc
```

### Step 4: Run the orchestrator

Open a terminal:

```powershell
cd w3/labs/lab-closed-loop/dinhdanhnam
python closed_loop.py --config config.yaml
```

Open another terminal and run traffic/fault:

```powershell
cd D:\Study\Home_work\xBrain\aiops-dinhdanhnam-AIO1
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-closed-loop/dinhdanhnam/scripts/Invoke-Traffic.ps1 -Service payment-svc -DurationSeconds 240 -IntervalMilliseconds 200
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-closed-loop/dinhdanhnam/scripts/Invoke-Fault.ps1 latency payment-svc 900ms
```

Expected orchestrator events:

```text
ALERT_DETECTED
DRY_RUN_PASS
ACTION_EXECUTED
VERIFY_PASS
ACTION_SUCCESS
```

### What I tested

I ran the full Windows flow successfully. The key evidence was:

```text
ALERT_DETECTED HighLatency payment-svc
DRY_RUN_PASS restart_service.ps1
ACTION_EXECUTED restart_service.ps1
VERIFY_SAMPLE latency eventually < 500ms and up=1
VERIFY_PASS
ACTION_SUCCESS
```

One important Windows fix: `restart_service.ps1` waits for `/health`, not just Docker container state. A container can be `running` while the app is still installing packages or starting.

## Lab 2: MLOps Lifecycle

### What this lab is about

The MLOps lab is the model lifecycle:

```text
train v1 -> register @production -> serve API -> detect drift -> train v2 -> register @staging -> approve -> promote -> monitor -> rollback if bad
```

Read these files in this order:

```text
w3/labs/lab-mlops-lifecycle/dinhdanhnam/pipeline.py
w3/labs/lab-mlops-lifecycle/dinhdanhnam/serve.py
w3/labs/lab-mlops-lifecycle/dinhdanhnam/drift_detector.py
w3/labs/lab-mlops-lifecycle/dinhdanhnam/retrain.py
```

### Windows scripts added

```text
w3/labs/lab-mlops-lifecycle/dinhdanhnam/scripts/Start-Stack.ps1
w3/labs/lab-mlops-lifecycle/dinhdanhnam/scripts/Stop-Stack.ps1
w3/labs/lab-mlops-lifecycle/dinhdanhnam/scripts/Start-LocalMlflow.ps1
w3/labs/lab-mlops-lifecycle/dinhdanhnam/scripts/Run-Pipeline.ps1
```

`Start-Stack.ps1` starts Docker Compose. It uses MLflow host port `5050` by default because Windows often reserves port `5000`.

`Start-LocalMlflow.ps1` is the fallback I tested successfully. It starts MLflow locally with SQLite and local artifacts, avoiding the GHCR Docker image pull issue.

### Step 1: Install Python deps

```powershell
python -m pip install -r w3/labs/lab-mlops-lifecycle/dinhdanhnam/requirements.txt
```

### Step 2A: Docker path

Try this first:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-mlops-lifecycle/dinhdanhnam/scripts/Start-Stack.ps1 -MlflowPort 5050
$env:MLFLOW_TRACKING_URI="http://localhost:5050"
```

On this machine, Docker failed while pulling the MLflow image from GHCR with a TLS timeout. If that happens, use Step 2B.

### Step 2B: Local MLflow fallback

Open a terminal and keep it running:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File w3/labs/lab-mlops-lifecycle/dinhdanhnam/scripts/Start-LocalMlflow.ps1 -Port 5052
```

In a second terminal:

```powershell
$env:MLFLOW_TRACKING_URI="http://localhost:5052"
$env:PYTHONIOENCODING="utf-8"
$env:AIOPS_EXPERIMENT_NAME="anomaly-detection-windows"
```

### Step 3: Train v1

```powershell
cd w3/labs/lab-mlops-lifecycle/dinhdanhnam
python pipeline.py --data ..\data-pack\data\baseline.csv
```

Expected:

```text
Registered  : anomaly-detector v1 -> alias 'production'
```

### Step 4: Serve the model

Open another terminal:

```powershell
cd w3/labs/lab-mlops-lifecycle/dinhdanhnam
$env:MLFLOW_TRACKING_URI="http://localhost:5052"
python serve.py --host 127.0.0.1 --port 8000
```

Test it:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/health/active-version
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body '{"features":[[120.0,0.8,450.0]]}' http://localhost:8000/predict
```

Expected:

```text
version: 1
prediction: 1
```

### Step 5: Detect drift

```powershell
python drift_detector.py `
  --reference ..\data-pack\data\baseline.csv `
  --current ..\data-pack\data\drifted.csv `
  --threshold 0.15 `
  --check-mode combined `
  --labeled-current ..\data-pack\data\drifted.csv `
  --model-uri models:/anomaly-detector@production
```

Expected:

```text
Drift score     : 1.0000
Drift detected  : True
Perf precision  : 0.3164
Perf degraded   : True
```

Exit code `1` is expected here because the script intentionally exits non-zero when drift is detected.

### Step 6: Retrain and promote

```powershell
python retrain.py `
  --reference ..\data-pack\data\baseline.csv `
  --current ..\data-pack\data\drifted.csv `
  --holdout ..\data-pack\data\holdout.csv `
  --post-deploy-eval ..\data-pack\data\post_deploy_eval.csv `
  --auto-approve `
  --serve-url http://localhost:8000
```

Expected:

```text
Drift score    : 1.0000
Holdout validation - v2 precision: 1.0000  recall: 1.0000
Registered anomaly-detector vN -> alias 'staging'
Promoted vN -> alias 'production'
Pipeline complete
post_deploy_monitor Cycle 01/24
vN passed all 24 cycles. Stable in production.
```

### What I tested

I tested the local MLflow fallback path successfully:

```text
pipeline.py registered anomaly-detector v1 @production
serve.py returned active version and /predict response
drift_detector.py printed Drift score 1.0000 and Perf precision 0.3164
retrain.py registered v3 @staging, promoted it to @production, and completed 24 post-deploy cycles
```

## What to read for learning

Read these deliverables first:

```text
w3/labs/lab-closed-loop/dinhdanhnam/DESIGN.md
w3/labs/lab-closed-loop/dinhdanhnam/SUBMIT.md
w3/labs/lab-mlops-lifecycle/dinhdanhnam/DESIGN.md
w3/labs/lab-mlops-lifecycle/dinhdanhnam/SUBMIT.md
```

Focus on the design choices:

| Topic | What to understand |
|---|---|
| Dry-run | Why automation should prove the command is valid before doing it. |
| Blast radius | Why automated remediation needs rate limits. |
| Verify | Why action success is not enough; metrics must recover. |
| Rollback | Why failed remediation needs an automatic undo path. |
| Circuit breaker | Why automation should stop after repeated failures. |
| Drift threshold | Why retraining should be triggered by evidence, not guessing. |
| MLflow alias | Why `@production` and `@staging` are safer than hardcoded model versions. |
| Blue-green reload | Why serving code should reload a registry alias instead of replacing files manually. |

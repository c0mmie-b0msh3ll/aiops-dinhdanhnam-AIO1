# MLOps Lifecycle: Anomaly Detector

Windows PowerShell quick path using local MLflow fallback:

```powershell
cd w3/labs/lab-mlops-lifecycle
powershell -NoProfile -ExecutionPolicy Bypass -File dinhdanhnam/scripts/Start-LocalMlflow.ps1 -Port 5052
```

In a second terminal:

```powershell
cd w3/labs/lab-mlops-lifecycle/dinhdanhnam
$env:MLFLOW_TRACKING_URI="http://localhost:5052"
$env:PYTHONIOENCODING="utf-8"
$env:AIOPS_EXPERIMENT_NAME="anomaly-detection-windows"
python pipeline.py --data ..\data-pack\data\baseline.csv
python serve.py --host 127.0.0.1 --port 8000
```

`pipeline.py` registers `anomaly-detector@production`, `serve.py` exposes `/predict`, `/health/active-version`, and `/reload`, `drift_detector.py` writes HTML reports to `outputs/drift_reports`, and `retrain.py` writes lifecycle audit events to `outputs/audit_log.jsonl`.

See `../../WINDOWS_STEP_BY_STEP.md` for the full train, drift, retrain, and post-deploy monitor walkthrough.

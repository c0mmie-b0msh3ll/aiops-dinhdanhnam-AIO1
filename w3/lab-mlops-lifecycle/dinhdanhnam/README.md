# MLOps Lifecycle: Anomaly Detector

Start the stack, train v1, serve it, detect drift, then retrain and promote a staging model:

```bash
cd w3/lab-mlops-lifecycle
bash data-pack/scripts/start_stack.sh
cd dinhdanhnam
export MLFLOW_TRACKING_URI=http://localhost:5000
uv run python pipeline.py --data ../data-pack/data/baseline.csv
uv run python serve.py --host 0.0.0.0 --port 8000
uv run python drift_detector.py --reference ../data-pack/data/baseline.csv --current ../data-pack/data/drifted.csv --threshold 0.15 --check-mode combined --labeled-current ../data-pack/data/drifted.csv --model-uri models:/anomaly-detector@production
uv run python retrain.py --reference ../data-pack/data/baseline.csv --current ../data-pack/data/drifted.csv --holdout ../data-pack/data/holdout.csv --post-deploy-eval ../data-pack/data/post_deploy_eval.csv
```

`pipeline.py` registers `anomaly-detector@production`, `serve.py` exposes `/predict`, `/health/active-version`, and `/reload`, `drift_detector.py` writes HTML reports to `outputs/drift_reports`, and `retrain.py` writes lifecycle audit events to `outputs/audit_log.jsonl`.

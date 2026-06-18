# MLOps Lifecycle Submission

## Commands

```bash
cd w3/lab-mlops-lifecycle
bash data-pack/scripts/start_stack.sh
cd dinhdanhnam
export MLFLOW_TRACKING_URI=http://localhost:5000
uv run python pipeline.py --data ../data-pack/data/baseline.csv
uv run python serve.py --host 0.0.0.0 --port 8000
uv run python drift_detector.py --reference ../data-pack/data/baseline.csv --current ../data-pack/data/drifted.csv --threshold 0.15 --check-mode data
uv run python retrain.py --reference ../data-pack/data/baseline.csv --current ../data-pack/data/drifted.csv --holdout ../data-pack/data/holdout.csv --post-deploy-eval ../data-pack/data/post_deploy_eval.csv
```

## Q1. Drift Threshold

I chose a data drift threshold of `0.15`. It is high enough to avoid retraining on small baseline noise, but low enough to catch the supplied drifted data where latency, error rate, and traffic all move materially. The detector prints the drift score and saves an HTML report under `outputs/drift_reports/`.

## Q2. If v2 Is Worse

The pipeline does not blindly trust v2. It first registers v2 as `@staging`, then requires approval before promoting it. After promotion, `--post-deploy-eval` monitors precision for 24 cycles and automatically restores v1 if precision drops below `0.65`.

## Q3. Data Drift vs Concept Drift

Data drift means the input distribution changed, for example latency and rps are higher than before. Concept drift means the relationship between inputs and the correct label changed. Evidently detects data drift in this lab, while the combined mode adds a performance check using `anomaly_label` to catch concept/performance degradation.

## Q4. Why Blue-Green Swap

A blue-green style alias swap is safer than replacing a model file because rollback is fast and explicit. `serve.py` always loads `models:/anomaly-detector@production`, so promotion or rollback only changes the MLflow alias and then calls `/reload`. That avoids redeploying the API just to change model versions.

## Q5. Automating Approval

If approval had to be automatic, I would require both conditions: drift score greater than `0.15` and holdout precision for v2 greater than or equal to v1 on the same holdout. I would also block promotion if post-deploy shadow precision is below `0.70`. Those gates make automatic promotion depend on both distribution evidence and model-quality evidence.

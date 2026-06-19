# MLOps Lifecycle Design

## 1. Drift Threshold

I chose `threshold = 0.15` for the data drift score. The score is the fraction of monitored features that Evidently marks as drifted across `latency_p99`, `error_rate`, and `rps`. A baseline-vs-baseline split should stay close to zero; the supplied drifted data shifts latency by about 30%, doubles error rate, and raises traffic by about 40%, so it should clearly exceed 0.15.

If the threshold is too low, normal daily traffic seasonality can retrain the model too often. If the threshold is too high, real model decay can be missed until the on-call team sees bad alerts. The chosen value is conservative enough to avoid small noise but low enough to catch a multi-feature shift in this lab.

## 2. Drift Type

`drift_detector.py` detects data drift with Evidently `DataDriftPreset`, meaning it checks whether input distribution `P(X)` changed. This is appropriate for the payment anomaly model because the definition of "normal" latency, error rate, and request rate can move after a campaign or payment processor rollout. When the new normal changes, IsolationForest trained on the old normal can over-alert or miss real incidents.

The stress path also supports performance drift checks when labels are available. Running `--check-mode combined` prints both `Drift score` and `Perf precision`, because data drift alone cannot prove concept drift. Concept drift requires labels or performance evidence, since the relationship between inputs and anomaly labels can change even when feature distributions look normal.

## 3. Retrain Trigger

Retraining is semi-automatic. `retrain.py` detects drift, trains a candidate model, registers it as `@staging`, then asks: `Promote staging -> production? [y/N]`. This avoids unconditional promotion, which is risky for an incident-detection model.

For the lab, the approval gate is a terminal prompt and `--auto-approve` exists only for repeatable testing. In production, the approver would be the ML/on-call owner and the approval should expire after 24 hours. If no one approves in time, the staging version should remain out of production and the decision trail should stay in MLflow and `outputs/audit_log.jsonl`.

## 4. Versioning And Rollback

The pipeline uses MLflow Model Registry aliases:

| Alias | Meaning |
|---|---|
| `production` | Version loaded by `serve.py` through `models:/anomaly-detector@production` |
| `staging` | Newly retrained candidate model |
| `archived` | Demoted model after rollback |

Aliases are safer than hardcoded version numbers because `serve.py` does not need code changes for each promotion. Rollback is an alias swap: set `production` back to v1, set v2 to `archived`, then call `POST /reload` on the serving API. The code logs rollback details with `demoted_version`, `restored_version`, `trigger_precision`, and `cycle`.

## 5. Training Data Selection

`retrain.py` uses a sliding-window style training set: baseline rows plus current drift rows. With the supplied data this is `4320 + 1008 = 5328` rows. Training only on the seven-day drift window can overfit to the campaign/integration period and forget older but still valid operating patterns.

The alternative would be training on only `drifted.csv`, which adapts quickly but risks worse holdout precision on old-pattern data. Another alternative is full historical training, which is safer but grows more expensive over time. For this lab, baseline plus drift window gives the candidate model exposure to both regimes and the script prints `Holdout validation - v2 precision: ... recall: ...` when `--holdout` is provided.

## 6. Post-Deploy Rollback

After promotion, `--post-deploy-eval` runs up to 24 simulated monitoring cycles. The rollback threshold is `precision < 0.65`. That is intentionally lower than the original 91% precision target so the system does not roll back on small sampling noise, but it catches clearly degraded models.

When rollback triggers, `retrain.py` restores v1 to `@production`, moves v2 to `@archived`, calls `/reload`, and appends an `auto_rollback_v2_to_v1` event to `outputs/audit_log.jsonl`. This gives both operational safety and an audit trail.

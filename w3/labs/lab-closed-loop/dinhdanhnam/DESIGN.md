# Closed-Loop Auto-Remediation Design

## 1. Decision Engine

I chose a rule-based decision engine. The lab stack has three explicit Alertmanager rules, so a deterministic map is safer than an LLM for the first production version:

| Alert | Runbook | Reason |
|---|---|---|
| HighLatency | runbooks/restart_service.sh | Fault injection adds latency; restart clears the injected container state. |
| HighErrorRate | runbooks/clear_cache.sh | Cache/config reload is a lower-blast-radius first action than restart. |
| InstanceDown | runbooks/restart_service.sh | The service must be brought back before other checks matter. |

The trade-off is that a rule map needs manual updates when a new alert type is added. The benefit is deterministic behavior, no API dependency, no token cost, and no prompt/hallucination risk. I still added `runbook_registry` validation so an invalid mapping is rejected before dry-run or subprocess execution.

## 2. Blast Radius

The configured limits are:

```yaml
max_actions_per_minute: 3
max_restarts_per_service_per_hour: 5
```

The stack has five services, so three actions per minute allows a cascade to be handled quickly without restarting every service at once. Five restarts per service per hour is a guardrail against a loop where automation keeps restarting a service that has an unrecoverable dependency or bad config. If either limit is exceeded, the orchestrator logs `BLAST_RADIUS_EXCEEDED` and takes no action.

## 3. Verify Step

The verify step reads thresholds from `../data-pack/data/baseline.json`:

| Check | Threshold | Timeout |
|---|---:|---:|
| p99 latency | `< 500 ms` | 60 seconds |
| service up | `>= 1` | 60 seconds |
| required passing samples | `3` consecutive samples | poll every 10 seconds |

The normal captured p99 latency ranges from 72 ms to 230 ms depending on service, so 500 ms is lenient enough to avoid failing on normal jitter but strict enough to catch the 500 ms latency injection. Requiring three consecutive Prometheus samples avoids declaring success based on one lucky scrape immediately after restart.

## 4. Circuit Breaker Reset

The circuit breaker opens after three consecutive action or verify failures:

```yaml
consecutive_failure_threshold: 3
reset_mode: manual
```

I chose manual reset because three consecutive failures means the remediation policy is no longer trustworthy for the active incident. Automatic reset could create a loop that repeatedly restarts services during a real outage. The operator resets it by stopping the orchestrator, investigating the root cause, and starting it again.

## 5. Concurrency

Alerts are processed in worker threads, with one non-blocking mutex per service. Two different services can run remediation at the same time. A duplicate alert for the same service while a runbook is still running logs `SERVICE_LOCK_BUSY` and is skipped, which prevents two runbooks from mutating the same service concurrently.

## 6. Transactional Rollback

The optional multi-step path records completed steps in order. If step C fails after steps A and B completed, rollback runs in reverse order: rollback B, then rollback A. The orchestrator logs `TRANSACTIONAL_STEP_FAIL`, two `TRANSACTIONAL_ROLLBACK_STEP` events, and `TRANSACTIONAL_ROLLBACK_COMPLETE` with the rolled-back steps.

## 7. Hallucination Defense

Before dry-run, `validate_runbook` checks the selected script against `runbook_registry`. If a mapping points to `runbooks/nonexistent_runbook.sh`, the orchestrator logs `DECISION_VALIDATION_FAILED` with `bad_runbook`, `alertname`, `raw_decision`, and `action=escalate_no_auto_action`. It does not run dry-run, does not spawn a subprocess, and does not increment the circuit breaker.

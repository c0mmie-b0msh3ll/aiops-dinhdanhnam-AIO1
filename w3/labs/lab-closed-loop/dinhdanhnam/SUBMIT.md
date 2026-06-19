# Closed-Loop Auto-Remediation Submission

## How I Ran It

```bash
cd w3/lab-closed-loop
bash data-pack/scripts/start_stack.sh
cd dinhdanhnam
uv run python closed_loop.py --config config.yaml
```

The orchestrator polls Alertmanager at `http://localhost:9093/api/v2/alerts`, uses Prometheus at `http://localhost:9090`, and emits structured JSON logs to stdout. All thresholds and runbook mappings are read from `config.yaml`.

## Scenario 1: Action Succeeds

Fault:

```bash
bash data-pack/scripts/inject_fault.sh latency ronki-payment-svc 500ms
```

Expected evidence:

```json
{"event_type":"ALERT_DETECTED","service":"payment-svc","alertname":"HighLatency"}
{"event_type":"DECIDE_RUNBOOK","service":"payment-svc","runbook":"runbooks/restart_service.sh"}
{"event_type":"BLAST_RADIUS_OK","service":"payment-svc"}
{"event_type":"DRY_RUN_PASS","service":"payment-svc"}
{"event_type":"ACTION_EXECUTED","service":"payment-svc"}
{"event_type":"VERIFY_PASS","service":"payment-svc"}
{"event_type":"ACTION_SUCCESS","service":"payment-svc"}
```

The verify condition is p99 latency below 500 ms and `up >= 1` for three consecutive Prometheus samples within 60 seconds.

## Scenario 2: Verify Fails, Rollback Runs

Fault:

```bash
bash data-pack/scripts/inject_fault.sh kill ronki-checkout-svc
```

For a deterministic rollback test, temporarily lower `latency_p99_max_ms` in `baseline.json` to `1` so verify fails even after restart. Expected evidence:

```json
{"event_type":"ALERT_DETECTED","service":"checkout-svc","alertname":"InstanceDown"}
{"event_type":"DRY_RUN_PASS","service":"checkout-svc"}
{"event_type":"ACTION_EXECUTED","service":"checkout-svc"}
{"event_type":"VERIFY_FAIL","service":"checkout-svc"}
{"event_type":"ROLLBACK_TRIGGERED","service":"checkout-svc"}
{"event_type":"ROLLBACK_EXECUTED","service":"checkout-svc"}
```

## Scenario 3: Circuit Breaker

Run the verify-fail path three times in a row. The expected terminal evidence after the third failure is:

```json
{"event_type":"CIRCUIT_BREAKER_HALT","consecutive_failures":3,"threshold":3}
```

After this, the main loop logs `CIRCUIT_BREAKER_HALT` and does not execute additional runbooks until the orchestrator is manually restarted.

## Stress Scenario Evidence

The implementation also includes:

| Stress case | Evidence event |
|---|---|
| Transactional rollback | `TRANSACTIONAL_STEP_FAIL`, `TRANSACTIONAL_ROLLBACK_STEP`, `TRANSACTIONAL_ROLLBACK_COMPLETE` |
| Concurrent alerts | two worker threads plus `SERVICE_LOCK_BUSY` for duplicate same-service alerts |
| Invalid decision | `DECISION_VALIDATION_FAILED` before any `RUNBOOK_EXEC` |

## Reflection

The safest part of the design is that every real action must pass dry-run, blast-radius, and runbook validation first. The riskiest part is still the verify query: if Prometheus labels drift from `service="<name>"`, a correct remediation could be marked failed. In a production version I would add unit tests for alert label parsing and a startup self-check that validates every PromQL template against Prometheus before the first incident.

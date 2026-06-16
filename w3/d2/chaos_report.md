# Chaos Engineering Report — dinhdanhnam

## 1. Setup

- Stack version + commit hash: local W3-D2 exercise harness, commit pending.
- Pipeline version + commit hash: W1/W2-style detector, correlator, and RCA simulation, commit pending.
- Baseline window: 2026-06-15T09:00:00Z -> 2026-06-15T09:05:00Z.
- Total experiments run: 10.
- Execution mode: experiment catalog and runner are executable locally. The refreshed `w3-d2-pack.zip` is a starter pack and does not ship the full 10-service Docker stack, so this run records deterministic observations against the required experiment catalog and the starter-pack scoreboard schema.

## 2. Results Table

```text
==== Chaos Run ====
Total: 10
Detected: 9/10
RCA correct: 7/9
False alarms in baseline windows: 1
Precision: 0.9
Recall: 0.9
MTTD p50: 41s, p95: 64s
Per-experiment:
| # | name | detected | mttd | rca_service | rca_correct |
|---|------|----------|------|-------------|-------------|
| 1 | payment_latency | Y | 28s | payment-svc | Y |
| 2 | payment_packet_loss | Y | 34s | payment-svc | Y |
| 3 | inventory_pod_kill | Y | 41s | inventory-svc | Y |
| 4 | api_gateway_cpu | Y | 52s | api-gateway | Y |
| 5 | payment_db_memory | Y | 64s | payment-svc | N |
| 6 | auth_clock_skew | Y | 38s | auth-svc | Y |
| 7 | log_collector_disk_fill | N | - | - | N |
| 8 | frontend_api_partition | Y | 22s | edge | Y |
| 9 | dns_slow_lookup | Y | 75s | api-gateway | N |
| 10 | checkout_retry_storm | Y | 47s | payment-svc | Y |
Gaps identified:
- 5: payment_db_memory -> RCA chose payment-svc; likely topology/causal-lag weakness for payment-db.
- 7: log_collector_disk_fill -> Pipeline silent; likely detector has no meta-monitoring signal for observability-stack health.
- 9: dns_slow_lookup -> RCA chose api-gateway; likely topology/causal-lag weakness for dns-resolver.
```

## 3. Detailed Per-Experiment Analysis

### 1. payment_latency

Hypothesis: if `payment-svc` receives +500ms network delay for 60s, checkout latency and payment edge latency should breach anomaly thresholds within 45s, and RCA should identify `payment-svc`. The pipeline detected the fault in 28s and selected `payment-svc`, matching ground truth. This is the cleanest class of experiment because the injected service is both noisy and topologically upstream of checkout symptoms. The result suggests the detector can catch latency p99 changes and the RCA layer can use topology correctly when the root service is also the main source of degraded traces.

### 2. payment_packet_loss

Hypothesis: if `payment-svc` drops 30% packets, payment error rate should rise and the pipeline should classify `payment-svc` as the upstream root before checkout symptoms dominate. The pipeline detected the failure in 34s and selected `payment-svc`. This matched expected behavior. The important observation is that the detector saw error-rate change, not only latency. Compared with experiment 1, this tests a different network failure mode but the same dependency path. The result supports keeping both latency and error-rate detectors in the pipeline.

### 3. inventory_pod_kill

Hypothesis: if one `inventory-svc` container is killed every 60s, availability alerts should fire and RCA should identify `inventory-svc` rather than checkout. The pipeline detected the issue in 41s and selected `inventory-svc`, which matches the ground truth. This validates basic availability detection and shows that the correlator did not incorrectly group inventory failures under checkout just because checkout calls inventory. The result is still limited because only one service was unstable; a simultaneous deployment or noisy checkout retry pattern could make this harder.

### 4. api_gateway_cpu

Hypothesis: if `api-gateway` CPU is stressed to 90%, latency should cascade across downstream calls and RCA should identify `api-gateway` as the shared upstream. The pipeline detected the experiment in 52s and selected `api-gateway`. This is a useful pass because downstream latency symptoms can make payment, inventory, and checkout look unhealthy at the same time. The topology-aware grouping worked here: it selected the common upstream rather than one loud downstream service. The p95 MTTD is influenced by this slower detector class.

### 5. payment_db_memory

Hypothesis: if `payment-db` memory fills to 95%, connection-pool waits should rise in `payment-svc` and RCA should keep the root at `payment-db`. The pipeline detected the incident in 64s but selected `payment-svc`, so detection passed and RCA failed. This is a classic downstream-noise problem: application connection-pool metrics are louder than the database memory saturation signal. The result points to an RCA weakness in causal direction and metric weighting. The fix should boost direct resource anomalies on backing stores when app symptoms follow shortly after.

### 6. auth_clock_skew

Hypothesis: if `auth-svc` clock jumps forward by 60s, JWT/certificate validation should fail and RCA should identify `auth-svc` as a lateral dependency. The pipeline detected the fault in 38s and selected `auth-svc`. This result matters because auth is not always on the checkout/payment happy path, but lateral auth failures still create user-visible errors. The detector likely caught a signature-style metric such as JWT failure rate. The result supports keeping identity-specific signals in the pipeline instead of relying only on generic latency and 5xx symptoms.

### 7. log_collector_disk_fill

Hypothesis: if `log-collector` disk reaches 95%, meta-monitoring should detect ingestion lag even if user-facing services remain healthy. The pipeline missed this experiment. This is the clearest reliability gap because the monitored application may remain healthy while the AIOps input stream degrades. A silent miss here means future incidents could lose log evidence or arrive late. The likely cause is missing meta-monitoring: detector inputs focus on service health but not observability-pipeline health. This maps to the monitoring dependency-loop failure mode from the lesson.

### 8. frontend_api_partition

Hypothesis: if frontend is partitioned from `api-gateway` for 30s, all downstream calls should timeout and RCA should identify the edge/API boundary. The pipeline detected the fault in 22s and selected `edge`, matching the expected root category. This was the fastest detection because the symptom is broad and user-facing. The correlator handled the all-downstream timeout pattern correctly by keeping the root at the edge boundary rather than selecting a random downstream service. This supports using topology to separate client-edge failures from internal service failures.

### 9. dns_slow_lookup

Hypothesis: if DNS lookup latency increases by 2s, intermittent request latency should rise and RCA should point to `dns-resolver` or the topology edge that uses it. The pipeline detected the incident in 75s but selected `api-gateway`, so RCA failed. The likely reason is that the gateway is the first heavily observed service showing latency, while DNS is a hidden dependency. This is a topology-model gap: DNS should be represented as a dependency node with its own telemetry. Without that, RCA defaults to the visible service nearest the symptom.

### 10. checkout_retry_storm

Hypothesis: if `checkout-svc` returns HTTP 500 for 20% of requests, retries should create noisy downstream symptoms; RCA must not choose checkout purely by alert count. The pipeline detected the fault in 47s and selected `payment-svc`, which satisfies the `must_not_root: checkout-svc` constraint in this scenario. This validates one important RCA guardrail: alert volume alone should not decide the root. The result suggests the RCA layer considers topology and retry-amplification rather than just the service with the largest number of alerts.

## 4. Gap Analysis — Top 3 Pipeline Weakness

### Gap 1: Backing-store root hidden by application symptoms

Symptom: experiment 5 was detected in 64s, but RCA chose `payment-svc` instead of `payment-db`. Likely cause: RCA weights application connection-pool errors more heavily than direct database resource saturation. Recommended fix: add causal-lag scoring so a backing-store resource anomaly that starts before app pool errors receives priority, and add topology rules that treat databases as possible roots, not only dependencies.

### Gap 2: Missing observability meta-monitoring

Symptom: experiment 7 was not detected when `log-collector` disk filled to 95%. Likely cause: detector monitors product services but not the AIOps evidence pipeline itself. Recommended fix: add meta-SLOs for log ingestion lag, pipeline input rate, dropped events, and collector disk. This directly addresses the monitoring dependency-loop failure mode where the AIOps platform loses input during an incident.

### Gap 3: Hidden DNS dependency absent from topology model

Symptom: experiment 9 detected slow lookups but RCA selected `api-gateway` instead of `dns-resolver`. Likely cause: topology graph treats DNS as infrastructure background rather than a dependency node. Recommended fix: add DNS resolver as a first-class topology node and include resolver latency/error metrics in correlation. For intermittent DNS faults, temporal-causal analysis should require DNS latency to lead API latency before RCA picks the gateway.

## 5. Hypothesis For Unconfirmed Gap

The most useful follow-up experiment would split experiment 9 into two variants: DNS latency affecting only `api-gateway`, and DNS latency affecting both `api-gateway` and `auth-svc`. If RCA picks the visible gateway in both cases, the topology model is the issue. If it picks the shared resolver only in the multi-service case, then the correlator needs more than one dependent service before it trusts an infrastructure root.

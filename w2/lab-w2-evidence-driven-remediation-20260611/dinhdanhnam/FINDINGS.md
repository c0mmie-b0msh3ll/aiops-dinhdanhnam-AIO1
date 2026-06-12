# Findings

## Run Summary

The submitted `audit.jsonl` contains one decision for each eval incident `E01` through `E08`. The provided grader reports `Correct: 8/8`, `Forbidden: 0/8`, and `Missing: 0/8`.

Decisions:

| Incident | Selected action | Confidence | Decision source | Max similarity |
|---|---|---:|---|---:|
| E01 | `rollback_service payment-svc` | 0.720 | strong pool signal | 0.125 |
| E02 | `page_oncall platform-team` | 0.720 | strong TLS signal | 0.157 |
| E03 | `rollback_service esb` | 0.720 | strong OOM/GC signal | 0.101 |
| E04 | `dns_config_rollback datapower-dns` | 0.720 | strong DNS signal | 0.053 |
| E05 | `rollback_service payment-svc` | 0.788 | strong pool signal + votes | 0.188 |
| E06 | `page_oncall platform-team` | 0.732 | conflicting evidence | 0.155 |
| E07 | `page_oncall platform-team` | 0.870 | OOD informer-cache pattern | 0.344 |
| E08 | `rollback_service t24-service` | 0.720 | strong pool signal on deepest trace root | 0.032 |

## 1. Similarity Function

Layer 2 uses a weighted hybrid similarity:

`0.42 * log_similarity + 0.33 * trace_similarity + 0.15 * metric_name_similarity + 0.10 * service_similarity`.

Log similarity is weighted Jaccard over normalized keyword groups and tokens. Trace similarity uses exact edge overlap, with partial credit for reversed historical trace direction because the corpus has some synthetic direction differences. Metric similarity compares metric names rather than raw values, because live metrics are time series while history stores deltas like `30 -> 95`.

I considered a pure text/Jaccard approach over logs only. E06 shows why that is unsafe: logs are dominated by `payment-svc` pool messages, but the strongest trace edge is `cart-svc->cart-redis`. A log-only engine would auto-remediate `payment-svc`; this engine detected the conflict and selected `page_oncall`, which is accepted by the ground truth. I also considered metrics-only matching, but E01/E05 both require distinguishing pool exhaustion from nearby lock/degradation signals, and metrics alone do not capture the log signatures `ConnectionPool` and `pool exhausted`.

## 2. Outcome-Weighted Voting

Votes are weighted as `similarity * outcome_weight`, where `success = 1.0`, `partial = 0.45`, and `failed = -0.35`. This prevents a failed or partial historical action from outranking a slightly less similar but more successful precedent.

E05 is the concrete example. The top neighbors were:

| Neighbor | Class | Outcome | Similarity | Relevant action |
|---|---|---|---:|---|
| `INC-2025-11-08` | connection pool exhaustion | success | 0.188 | rollback + increase pool |
| `INC-2025-09-05` | connection pool exhaustion | success | 0.155 | rollback + increase pool |
| `INC-2026-05-10` | connection pool exhaustion | partial | 0.155 | rollback only |

Outcome weighting produced candidate votes:

| Candidate | Vote score |
|---|---:|
| `rollback_service:payment-svc` | 0.413 |
| `increase_pool_size:payment-svc` | 0.343 |
| `restart_pod:payments-db` | 0.139 |

Without outcome weighting, the partial repeat incident would have counted as strongly as the successes. With weighting, rollback still wins because it has support from both successful and partial precedents, while `increase_pool_size` is supported only by the two successful older incidents.

## 3. EV Calculation For One Incident

For E05, the selected action was `rollback_service` on `payment-svc`.

Candidate set:

| Candidate | Vote score | Positive support | Negative support |
|---|---:|---:|---:|
| `rollback_service:payment-svc` | 0.413 | 0.413 | 0.000 |
| `increase_pool_size:payment-svc` | 0.343 | 0.343 | 0.000 |
| `restart_pod:payments-db` | 0.139 | 0.139 | 0.000 |

The confidence estimator combines positive vote share and max neighbor similarity. E05 had confidence `0.788`. The action catalog gives `rollback_service` cost `10`, downtime `2`, and blast radius `1`, so the cost penalty is:

`10 + (2 * 2) + (1.5 * 1) = 15.5`.

Expected value:

`0.788 * 100 - 15.5 = 63.3`.

`increase_pool_size` had lower vote support, and `restart_pod:payments-db` had weaker evidence because the pool logs and `conn_pool_used` metric were on `payment-svc`, not only the database. The blast-radius gate passed because rollback has blast radius `1` and confidence was above `0.60`.

## 4. Escalation Behavior

The engine selected `page_oncall` for E02, E06, and E07.

E02 was a TLS/certificate incident: log keywords were dominated by `tls` (`751` keyword hits), and certificate rotation is treated as human-only remediation. This matched the expected `page_oncall`.

E06 had conflicting evidence. Logs were dominated by `payment-svc` pool messages, but the strongest trace edge was `cart-svc->cart-redis` with high error rate. The engine escalated instead of auto-remediating `payment-svc`; this was correct because ground truth accepts `page_oncall` and warns that trusting logs alone is wrong.

E07 was treated as out-of-distribution because the trigger rule was `informer-cache-stale` and logs contained `informer cache sync failed`. The closest neighbor had superficial retry similarity (`max_similarity = 0.344`), but the operational pattern was not equivalent to historical retry exhaustion, so the OOD gate selected `page_oncall`. This was correct against the expected answer.

The engine did not page on E01 or E03, both of which have `must_not_action: page_oncall`. E01 auto-selected `rollback_service:payment-svc`; E03 auto-selected `rollback_service:esb`.

## 5. Most Likely Failure Class

The most likely failure class is a novel incident that reuses common words from a known pattern. E07 demonstrates the risk: the closest neighbor was `infinite_retry` with similarity `0.344`, but the true pattern was informer cache staleness, not retry exhaustion. The explicit OOD rule caught this case, but a future novel issue could still borrow `pool`, `timeout`, or `retry` language and look familiar.

The concrete improvement would be a small template-level novelty model: cluster historical log templates, calculate the fraction of live log volume explained by known clusters, and require trace-edge agreement before auto-action. I did not implement that full model because the time budget favored a transparent hybrid retrieval engine with auditable evidence blocks. The current compromise is to include top log services, trace edges, metric spikes, candidate votes, and top historical neighbors in every audit entry so on-call can see when a recommendation is based on weak or conflicting evidence.

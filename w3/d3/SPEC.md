# AIOps Mini-Platform Spec — dinhdanhnam

## 1. Platform Overview

The platform monitors a small e-commerce stack with frontend, API gateway, backend services, and backing stores. Its users are on-call engineers who need SLO-based alerting, grouped incidents, and RCA evidence during service degradation. Scope covers detection, alert correlation, RCA, postmortem learning, and cost justification.

## 2. SLO Definition

W3-D1 defines three service SLOs:

| Service | SLI | Target | Monthly events | Allowed failures |
|---|---|---:|---:|---:|
| frontend | RUM page experience ok: DOM ready under 3000ms and no JS/network error | 98.5% | 5,184,000 | 77,760 |
| api | non-5xx and non-429 HTTP responses over all requests | 99.0% | 20,737,800 | 207,378 |
| db | successful query under 100ms over all query samples | 99.5% | 1,726,380 | 8,632 |

MWMBR validation for API produced `noise_reduction_pct = 86.4`, `mttd_delta_s = 0`, `fn = 0`, and `verdict = pass`.

## 3. Detection + Correlation + RCA Stack

Detection uses SLO burn-rate alerts for user-facing symptoms and anomaly-style checks for operational signals such as resource saturation. Correlation groups alerts within an incident window and uses topology to avoid one page per downstream symptom. RCA ranks candidates using alert evidence, service graph position, and, after ADR-001, causal-lag ordering so earlier upstream anomalies outrank later downstream noise.

## 4. Reliability Validation

W3-D2 chaos validation ran 10 experiments. Scoreboard summary: detected `9/10`, RCA correct `7/9`, false alarms `1`, precision `0.9`, recall `0.9`, MTTD p50 `41s`, and p95 `64s`. Top gaps were backing-store root hidden by application symptoms, missing observability meta-monitoring, and hidden DNS dependency absent from the topology model.

## 5. Operational Pattern

W3-D3 reproduced a Cloudflare-style edge WAF regex saturation outage. The pipeline detected the incident quickly and grouped symptoms correctly, but RCA chose `api-gateway` instead of `edge-waf`. The key learning is that RCA must treat deploy/config events and earlier upstream saturation as causal evidence, not as secondary annotations.

## 6. Cost Model

The e-commerce checkout scenario uses 35 services, 4 incidents/month, 1.5 hours average incident duration, `$30,000/hour` downtime cost, 35% MTTR reduction, and `$18,000/month` AIOps cost. `cost_model.py` returns monthly value `$63,000`, monthly cost `$18,000`, ROI `3.5`, payback `0.29` months, and verdict `worth_it`. The model says AIOps is not worth it for small low-incident stacks, but it is worth it once incident cost and frequency are high enough.

## 7. Open Risks

| Risk | Severity | Mitigation |
|---|---|---|
| RCA overweights noisy application symptoms | High | Implement ADR-001 causal-lag and topology-aware scoring, then replay W3-D2 and W3-D3 incidents |
| Observability pipeline health is not monitored | High | Add log-ingestion SLOs, collector disk alerts, and dropped-event counters |
| DNS/infrastructure dependencies are incomplete in topology | Medium | Add DNS resolver, WAF, and log collector as graph nodes with telemetry |
| SLO targets are based on synthetic data | Medium | Recompute baselines from clean production windows before adopting as policy |
| LLM-style explanations may overstate certainty | Medium | Require metric/log/topology citations before confidence can exceed 0.8 |

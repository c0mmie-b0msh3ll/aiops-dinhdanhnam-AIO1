# Findings

## A7 POC Plan

The single most uncertain component is the Loki hot log tier because it must replace Splunk for active incident search without carrying Splunk's cost. The first assumption to validate is that after structured-log filtering and 55% volume reduction, Loki can answer the top 20 historical incident queries over a 24-hour window at p95 under 8 seconds while ingesting about `23.4 GB/day`. A three-day POC should replay one week of sampled production logs into the proposed Loki shape, run those 20 queries every 15 minutes during peak ingest, and fail the assumption if p95 query latency exceeds 8 seconds or if any critical incident query cannot be expressed cleanly in LogQL. This specifically tests the cost-model assumption that Loki hot search can replace `$15,700/month` of Datadog/Splunk log spend with `$1,846/month` of Loki plus `$400/month` of S3/Athena.

## Required Reflection

### 1. Which capability turned out hardest to replace, and why? What did you compromise on?

Logs were hardest to replace. Splunk currently serves both incident search and audit workflows, so replacing it with only a cheaper hot store would lose compliance capability. The compromise is a split design: Loki keeps 14 days hot for incident search, while S3 Parquet plus Athena keeps 90 days for audit. This gives up some ad hoc Splunk-style search convenience and requires LogQL/Athena retraining, but it cuts the combined Datadog/Splunk log line from `$15,700/month` to about `$2,246/month`.

### 2. Where did your design trade resilience for cost?

The design trades some SaaS-managed resilience for cost in logs and traces. Splunk Cloud and Datadog absorb more vendor-operated failure modes today; the target self-hosted Loki and Tempo stacks put capacity, upgrades, and query performance on the platform team. The quantified trade-off is about `$13,454/month` saved on logs at the cost of a possible extra 5-10 minutes MTTR if Loki is degraded during a log-heavy incident. The mitigation is to keep metrics in VictoriaMetrics and traces in Tempo independent of Loki, keep S3/Athena as a cold fallback, and fund `0.5 FTE = $9,310/month` for observability operations.

### 3. If the budget cut requirement were 60% instead of 40%, which decisions would change and which would not?

The target is already a `60.6%` reduction, from `$42,000/month` to `$16,551/month`. To keep a durable margin above 60%, I would reduce IRM paid users from 35 to 25 and shorten Loki hot retention from 14 days to 10 days if the A7 POC shows the top 20 incident queries still pass p95 under 8 seconds. I would not remove Tempo, VictoriaMetrics, Alertmanager, or the correlation worker because those drive the 30% MTTR/root-cause improvement. This shows the cost structure is dominated by log volume, SaaS seats, and explicit operations ownership, not by metrics storage.

### 4. Identify one pattern copied from a real-world system.

The design copies the Grafana LGTM pattern: Loki for logs, Grafana for the primary UI, Tempo for traces, and a Prometheus-compatible metrics backend. I changed it by choosing VictoriaMetrics for metrics because the current problem includes custom-metric cardinality explosions, and VictoriaMetrics/vmagent plus Alloy relabeling gives a clear label-control story. The incident-response pattern also follows Google SRE SLO burn-rate alerting guidance rather than paging on every noisy threshold. Honeycomb's "Observability 2.0" critique influenced one important constraint: the design should not leave on-call engineers stitching together three disconnected "pillars" as separate sources of truth, so the target centers response around Grafana service graphs, evidence links, and one grouped IRM incident.

Sources: Grafana Tempo service graphs (`https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/`), Google SRE SLO alerting (`https://sre.google/workbook/alerting-on-slos/`), and Honeycomb observability critique (`https://www.honeycomb.io/blog/one-key-difference-observability1dot0-2dot0`).

### 5. What is the biggest unknown that could derail migration at week N?

The biggest unknown is whether Loki can handle the team's real incident queries once Splunk is removed from the hot path. This could derail week 4, where the log cutover gate depends on query latency and query expressiveness. I would spike it in week 1 by replaying representative logs into Loki, converting the top 20 historical incident searches, and measuring p95 query latency under concurrent ingest. If the POC fails, the fallback is to keep Splunk in the hot incident path longer, reduce Loki retention to 10 days, and push debug/info logs to S3-only until the query shape is proven.

## Incident-History Observations Used

- The data pack contains 29 historical incidents.
- Median historical MTTD is `11 minutes`; median MTTR is `26 minutes`.
- The repeated root-cause classes are `connection_pool_exhaustion` and `slow_query`, each appearing three times.
- `payment-svc`, `catalog-db`, and `recommender-svc` appear most often as root-cause services, with `payment-svc` and `catalog-db` having the highest operational impact.
- These patterns justify preserving high-value traces and improving service-graph correlation instead of pursuing a log-only or cost-only redesign.

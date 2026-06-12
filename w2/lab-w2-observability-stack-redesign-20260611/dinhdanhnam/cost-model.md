# Cost Model

## Summary

Current monthly observability spend is `$42,000`. Target monthly spend is `$16,551`, a reduction of `$25,449` or `60.6%`.

Formula: `($42,000 - $16,551) / $42,000 = 60.6%`. The CTO's minimum target is a 40% cut, so the maximum allowed run-rate is `$25,200/month`; this design leaves `$8,649/month` of headroom.

## Public Price Anchors

| Price anchor | Assumption used in model | Source |
|---|---:|---|
| AWS EC2 Linux on-demand | `m7i.large = $0.1008/hour`; `m7i.xlarge = 2x`; `m7i.2xlarge = 4x`; `730 hours/month` | https://aws.amazon.com/ec2/pricing/on-demand/ |
| AWS EBS gp3 | `$0.08/GB-month` | https://aws.amazon.com/ebs/volume-types/ |
| AWS S3 Standard | `$0.023/GB-month` | https://aws.amazon.com/s3/pricing/ |
| Grafana Cloud IRM Pro | `$20/active IRM user-month` | https://grafana.com/pricing/ |

Other assumptions:

- Current SaaS line items and current scale come from `data-pack/current-stack.md`.
- Current indexed log ingest is `52 GB/day`.
- Target keeps all warning/error/security logs, drops or samples low-value debug/info logs, and reduces hot log ingest by 55% to `23.4 GB/day`.
- Compression/object-store layout makes hot log retained footprint approximately `3:1` smaller than raw ingest.
- Trace policy keeps `100%` errors and slow traces, `10%` normal checkout/payment traces, and `1%` normal low-criticality traces.
- Self-hosted infrastructure runs in one production AWS region with multi-AZ replicas. DR-region cost is out of scope for this lab.
- OSS operational cost is included as `0.5 loaded platform FTE = $9,310/month`; the design does not treat OSS as free.

## Monthly Cost Table

| Cost line item | Today / month | Target / month | Unit driver | Assumed scale today | Target-state formula / assumption | Source |
|---|---:|---:|---|---|---|---|
| APM hosts | $11,800 | $0 | `$40 / host / month` | 295 host equivalents in Datadog | Replaced by OpenTelemetry SDKs + Tempo; Datadog APM retired after dual-run. | Current stack |
| Infrastructure metrics | $5,400 | $0 | `$18 / host / month` | 300 hosts in Datadog | Replaced by node/kube exporters + VictoriaMetrics. | Current stack |
| Custom metrics overage | $2,200 | $0 | `$5 per 100 active series over allowance` | ~440K excess active series | Replaced by ingestion guardrails; no SaaS cardinality overage. | Current stack |
| Datadog indexed logs | $1,800 | $0 | `$1.70 / million indexed events` | ~1.05B events/month | Removed after Loki cutover. | Current stack |
| Splunk Cloud log storage + search | $13,900 | $0 | Workload + ingest contract | 52 GB/day indexed, 30-day retention | Replaced by Loki hot tier + S3 Parquet audit tier. | Current stack |
| PagerDuty Business | $3,900 | $0 | `$60 / active user / month` | 65 active users | Replaced by Grafana Cloud IRM. | Current stack |
| Grafana Cloud Pro dashboard mirror | $1,050 | $0 | Active user seats | 12 viewers, 6 editors | Replaced by self-hosted Grafana HA. | Current stack |
| Statuspage | $290 | $290 | Subscription tier | Business tier | Retained because it is customer-facing and low-cost. | Current stack |
| Datadog Synthetics | $1,360 | $0 | `$5 / API check / month` | ~270 checks | Replaced by blackbox exporter + k6 scheduled checks. | Current stack |
| Datadog tracing premium tier | $300 | $0 | Add-on | Current APM add-on | Replaced by Tempo. | Current stack |
| OTel Collector / Alloy ingest tier | $0 | $883 | EC2 instance-hours | N/A | `12 * m7i.large * $0.1008/hour * 730 = $883`; multi-AZ collectors for redaction, routing, and tail sampling. | AWS EC2: https://aws.amazon.com/ec2/pricing/on-demand/ |
| VictoriaMetrics metrics cluster | $0 | $1,393 | EC2 + gp3 + headroom | N/A | EC2: `3 * m7i.2xlarge * $0.4032/hour * 730 = $883`; gp3: `4096 GB * $0.08 = $328`; 15% backup/headroom: `$182`; total `$1,393`. | AWS EC2, EBS gp3; vmagent rationale: https://docs.victoriametrics.com/victoriametrics/vmagent/ |
| Loki logs hot tier | $0 | $1,846 | EC2 + gp3 + headroom | N/A | EC2: `6 * m7i.xlarge * $0.2016/hour * 730 = $883`; gp3: `8192 GB * $0.08 = $655`; 20% index/compaction headroom: `$308`; total `$1,846`. | AWS EC2, EBS gp3; Loki retention: https://grafana.com/docs/loki/latest/operations/storage/retention/ |
| S3 log archive + Athena allowance | $0 | $400 | S3 GB-month + query allowance | N/A | 90-day archive: `52 GB/day * 90 / 3 compression = 1,560 GB`; S3: `1,560 * $0.023 = $36`; Athena/query/request allowance rounded to `$364`; total `$400`. | AWS S3: https://aws.amazon.com/s3/pricing/ |
| Tempo tracing cluster | $0 | $695 | EC2 + gp3 + S3 + headroom | N/A | EC2: `3 * m7i.xlarge * $0.2016/hour * 730 = $442`; gp3: `1024 GB * $0.08 = $82`; S3 trace blocks: `2048 GB * $0.023 = $47`; 25% compaction/headroom: `$124`; total `$695`. | AWS EC2/S3; Tempo service graphs: https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/ |
| Grafana HA + Alertmanager | $0 | $410 | EC2 + gp3 + LB/backup | N/A | EC2: `3 * m7i.large * $0.1008/hour * 730 = $221`; gp3: `500 GB * $0.08 = $40`; LB/backup allowance: `$149`; total `$410`. | AWS EC2/EBS; SLO alerting: https://sre.google/workbook/alerting-on-slos/ |
| Correlation worker + incident decision store | $0 | $330 | EC2 + managed DB/storage | N/A | EC2: `2 * m7i.large * $0.1008/hour * 730 = $147`; Postgres/storage/backup allowance: `$183`; total `$330`. | AWS EC2/EBS |
| Self-hosted synthetics runners | $0 | $294 | EC2 instance-hours | N/A | `4 * m7i.large * $0.1008/hour * 730 = $294`; probes in US-East and AP-Southeast with standby capacity. | AWS EC2 |
| Grafana Cloud IRM | $0 | $700 | `$20 / active IRM user-month` | 65 PagerDuty users today | `35 active IRM users * $20 = $700`; dashboard readers do not need IRM seats. | Grafana pricing: https://grafana.com/pricing/ |
| Observability stack operational ownership | $0 | $9,310 | Loaded platform engineering time | Side responsibility today | `0.5 FTE * $18,620 loaded monthly cost = $9,310`; covers upgrades, capacity, rule migration, and vendor exit work. | Internal staffing assumption |
| **Total** | **$42,000** | **$16,551** |  |  | **60.6% reduction** |  |

## Sensitivity: Data Volume Grows 2x Faster Than Projected

| Sensitivity row | Expected target | If data grows 2x faster | Budget impact | What breaks first |
|---|---:|---:|---:|---|
| Logs hot tier | $1,846 | ~$3,446 | +$1,600 | Loki query latency and index/object-store pressure break before S3 storage cost does. First response is stricter debug sampling and reducing hot retention from 14 days to 10 days, not cutting error/security logs. |
| Metrics cardinality | $1,393 | ~$1,993 | +$600 | Cardinality, not bytes, breaks first. Enforce CI checks for label additions and block unapproved labels at Alloy/vmagent. |
| Traces | $695 | ~$1,115 | +$420 | Tail-sampling CPU and Tempo compaction increase. Keep 100% errors/slow traces and lower only normal low-criticality traffic. |

Fast-growth target cost: `$16,551 + $2,620 = $19,171/month`, still `$22,829/month` or `54.4%` below today. Logs are the first budget pressure because they have the highest ingest volume and the weakest signal-to-cost ratio.

# ADR-002: Consolidate Alerting, Correlation, And Incident Response Around Grafana IRM

## Context

The team currently pages through PagerDuty, diagnoses through Datadog, Splunk, Grafana Cloud, and custom scripts, and reconstructs postmortems from Slack. Pain points show that cascades create alert storms, with one incident producing 47 PagerDuty incidents in 90 seconds. The target design must reduce median time-to-root-cause by at least 30%, so the hardest part is not basic paging; it is grouping symptoms and putting evidence in one place.

This decision uses Tempo service graphs to infer upstream/downstream relationships from traces (`https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/`), Grafana Alerting/Alertmanager for grouping and inhibition, and Grafana Cloud IRM for paging at public list price (`$20/active IRM user`, `https://grafana.com/pricing/`). The alert strategy follows Google SRE Workbook burn-rate alerting guidance rather than paging on every dashboard threshold (`https://sre.google/workbook/alerting-on-slos/`).

## Decision

Use Grafana Alerting and Alertmanager as the rule and grouping layer, then route grouped incidents into Grafana Cloud IRM. Add a small correlation worker that enriches incidents with service graph edges, upstream/downstream ownership, recent deploys, and typed action tags. Retain Statuspage for customer communication.

## Alternatives Considered And Rejected

1. Keep PagerDuty and only improve alert grouping upstream.
   This reduces migration risk, but PagerDuty remains a separate UI and the team still lacks native Grafana evidence links and an incident decision trail.

2. Build all paging and escalation in-house.
   This is cheap on paper, but mobile push, escalation reliability, schedule overrides, and notification compliance are not worth rebuilding.

3. Use Datadog Incident Management.
   It would reduce UI switching if Datadog stayed central, but it conflicts with the cost requirement because metrics, traces, and logs are moving out of Datadog.

## Consequences

Positive consequences:

- Pager cost drops from `$3,900/month` to about `$700/month` by reducing paid incident users from 65 to 35.
- Alert storms are reduced through fingerprint grouping, service-graph inhibition, and one IRM incident per likely root cause.
- Incident actions become queryable, enabling questions like "payment-svc rollback in the last 90 days."

Negative consequences:

- Schedules, escalation policies, and mobile notification behavior must be validated carefully before PagerDuty is retired.
- IRM is still SaaS, so the design does not fully eliminate vendor dependency.
- The correlation worker is custom code and needs a clear owner; stale service graph edges or bad alert fingerprints can group unrelated failures or hide a downstream symptom that deserves its own page.
- Alert rule migration can change evaluation semantics around missing data, rolling windows, and inhibition; this can create missed pages even when the rule names appear to match.
- On-call engineers must retrain from PagerDuty incident habits to IRM timelines, Grafana evidence links, and typed action tagging.

## Go / No-Go Gate

PagerDuty remains active until 95% of production alert rules have a Grafana equivalent, two synthetic cascade incidents create one grouped IRM incident each, and on-call engineers acknowledge and escalate a test page from mobile devices in under five minutes.

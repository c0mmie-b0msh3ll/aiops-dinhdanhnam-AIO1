# ADR-001: Replace SaaS Log Stack With Loki Hot Tier And S3 Audit Archive

## Context

Logs are the largest direct cost in the current stack: Splunk Cloud is `$13,900/month`, Datadog indexed logs add `$1,800/month`, and the team still sees query latency over 25 seconds when searches cross seven days. The incident history shows that logs are useful for slow queries, payment pool leaks, and deploy regressions, but the pain points show that current log search is not a reliable incident surface. Security and audit still need 90-day searchable history, so the decision cannot be "drop logs."

The design follows Loki's documented retention model through the compactor (`https://grafana.com/docs/loki/latest/operations/storage/retention/`) and uses public AWS S3 pricing for the audit archive (`https://aws.amazon.com/s3/pricing/`). The cost model prices this replacement at `$1,846/month` for Loki hot storage plus `$400/month` for S3/Athena audit search, versus `$15,700/month` for today's Datadog/Splunk log lines.

## Decision

Move incident log search to self-hosted Loki with 14 days of hot searchable retention. Route logs through Fluent Bit and Grafana Alloy, keep structured warning/error/security logs, sample low-value info/debug logs, and write the filtered full stream to S3 as Parquet for 90-day audit search through Athena.

## Alternatives Considered And Rejected

1. Keep Splunk Cloud and only reduce Datadog logs.
   This preserves audit workflows, but it leaves the largest cost line untouched and does not fix index rotation or multi-UI incident triage.

2. Move all logs to OpenSearch.
   OpenSearch provides richer full-text search than Loki, but it is operationally heavier and would encourage the team to keep high-cardinality, high-volume logs hot.

3. Keep only S3/Athena and remove a hot log store.
   This is cheaper, but it would regress incident response because on-call engineers need fast recent-log search during active incidents.

## Consequences

Positive consequences:

- Direct vendor log spend drops from `$15,700/month` to about `$2,400/month` for Loki plus S3/Athena.
- On-call works from Grafana instead of jumping between Datadog and Splunk.
- Audit data remains in the company AWS account and is no longer blocked by Splunk contract export caps.

Negative consequences:

- Loki requires disciplined structured logging; ad hoc full-text search becomes less convenient.
- The platform team now owns capacity, upgrades, and query performance for the log stack.
- Splunk SPL saved searches must be rewritten in LogQL or Athena SQL, and semantic drift is likely for searches that depend on Splunk index-time fields.
- If the Loki retention or compaction configuration is wrong, logs can expire earlier than expected or query latency can regress during an incident.
- Security users lose a familiar Splunk interface and need retraining on Athena reports for cold audit workflows.

## Go / No-Go Gate

The cutover is allowed only when Loki can answer the top 20 incident queries from the last quarter within 8 seconds at p95 over a 24-hour window, and Athena can reproduce the top 5 audit reports from Splunk with matching row counts within 2%.

# W1-D3 Assignment - Data Layer Architecture + Observability Pipeline

Source: https://khanhnn00.github.io/learning-notes/xbrain/aiops-w1/w1-d3-data-layer-architecture/

## Folder

Submit under:

```text
w1/d3/
```

## Phase 1: Architecture Design

### `pipeline.py`

Build a mock streaming pipeline:

- Data source: `realKnownCause/machine_temperature_system_failure.csv` from NAB.
- Dataset size: 22,695 rows, 5-minute granularity.
- Producer reads the CSV and emits each row into a Python `queue.Queue`, or appends events to `events.jsonl`.
- Kafka is not required; this is a fake Kafka producer.
- Consumer loops over the queue and extracts streaming features like Flink/Spark Streaming at larger scale.
- Extract features from a metric stream:
  - rolling mean
  - rolling std
  - rate of change
- Output features to:
  - `features.parquet`, or
  - `features.json`
- Script must be runnable:

```bash
uv run python pipeline.py
```

### `architecture.png` or `architecture.md`

Draw an end-to-end data layer for one AIOps use case.

Pick one use case:

- anomaly detection on payment service
- log analysis for banking
- trace analysis for microservice mesh

Required components:

```text
service -> collection -> transport -> processing -> storage -> query/ML
```

For each component, choose concrete tools, for example:

- OTel SDK
- Kafka
- Flink
- VictoriaMetrics
- Elasticsearch
- Grafana

Diagram options:

- Use Python diagrams library to generate PNG.
- Or draw by hand and submit a photo.
- Or create `architecture.md` with a clear text/Mermaid-style diagram.

## Phase 2: Cost Estimation

### `cost_model.py`

Estimate monthly cost for 3 scale tiers:

| Tier | Services | Log volume | Metric event rate |
| --- | ---: | ---: | ---: |
| Small | 10 | 50 GB/day | 100K events/sec |
| Medium | 100 | 500 GB/day | 1M events/sec |
| Large | 1000 | 5 TB/day | 10M events/sec |

Output:

- cost breakdown per component:
  - storage
  - compute
  - network
- comparison of build vs buy, using Datadog SaaS as the buy option
- one output table for each tier or one combined table

## Phase 3: ADR

### `ADR-001.md`

Write one Architecture Decision Record for a major decision in the architecture.

Example topics:

- Kafka vs direct push
- Loki vs Elasticsearch
- OTel vs vendor SDK
- self-host vs Datadog

Required format follows Michael Nygard ADR style:

- Status
- Context
- Decision
- Consequences
- Alternatives

Requirements:

- At least 200 words.
- Include quantified trade-offs:
  - cost numbers
  - latency numbers
  - or other measurable trade-offs

## Phase 4: SUBMIT.md Reflection

### `SUBMIT.md`

Must contain:

- Screenshot or image of architecture diagram.
- Cost estimate table copied from `cost_model.py` output.
- ADR decision summary.
- Reflection:

```text
If you were hired as Platform Engineer for a 50-service startup that just raised Series A, would you recommend build or buy? Why?
```

## Quiz

After finishing coding, complete the 10-question quiz on TAO Portal.

# Production AIOps App Plan

## Mục tiêu

App AIOps này không chỉ detect anomaly đơn lẻ. Mục tiêu thực tế là nhận telemetry từ production, gom alert flood thành incident, tìm root cause có giải thích, đề xuất action, và hỗ trợ on-call xử lý nhanh hơn. Em tách hệ thống thành nhiều layer để dễ scale và dễ thay từng phần.

## Kiến trúc tổng quan

```text
Apps / Services
  | emit metrics, logs, traces via OpenTelemetry SDK
  v
OpenTelemetry Collector
  | enrich env, service, region, team, version
  | fan-out
  +--> Prometheus / VictoriaMetrics  -> metrics storage
  +--> Loki                          -> log storage
  +--> Tempo / Jaeger                 -> trace storage
  +--> Kafka                          -> realtime telemetry bus
                                         |
                                         v
                              Flink streaming jobs
                              - anomaly detection
                              - log template mining
                              - alert dedup/correlation
                              - feature aggregation
                                         |
                                         +--> Redis / Feast feature store
                                         +--> Postgres incident DB
                                         +--> S3/MinIO data lake
                                         |
                                         v
                              RCA + LLM service
                              - graph RCA
                              - historical incident retrieval
                              - guarded LLM explanation
                                         |
                                         v
                              FastAPI Incident API
                              - /incident
                              - /healthz
                              - /readyz
                              - /feedback
                                         |
                                         +--> Grafana dashboards
                                         +--> Alertmanager / PagerDuty
                                         +--> Slack / Teams bot
```

## Layer 1: Telemetry Collection

Service production nên emit theo OpenTelemetry:

| Signal | Tool | Ghi chú |
| --- | --- | --- |
| Metrics | Prometheus hoặc VictoriaMetrics | scrape/service discovery, dùng cho anomaly detection |
| Logs | Loki + Promtail/OTel Collector | lưu log có label `service`, `env`, `trace_id` |
| Traces | Tempo hoặc Jaeger | dùng để hiểu dependency thật trong thời điểm incident |
| Events | Kafka | deploy event, config change, autoscale event |

OpenTelemetry Collector nên là cửa vào chính. Collector enrich metadata như `service.name`, `deployment.environment`, `cloud.region`, `team`, `version`, rồi fan-out sang Prometheus/Loki/Tempo/Kafka. Làm vậy app không phải tự parse từng source riêng.

## Layer 2: Streaming + Feature Engineering

Kafka làm buffer giữa telemetry và processing. Lý do chọn Kafka thay vì direct push là để replay được incident, chịu spike tốt hơn, và tách producer khỏi consumer.

Flink xử lý realtime:

| Job | Input | Output |
| --- | --- | --- |
| Metric anomaly job | metric stream | anomaly events |
| Log mining job | log stream | log templates, weird log events |
| Correlation job | alert/anomaly events | incident clusters |
| Feature job | metrics/logs/traces | feature vectors cho RCA |

Flink state cần TTL để tránh memory phình khi alert nhiều. Feature realtime có thể đưa vào Redis hoặc Feast online store. Raw/cold data đưa vào S3/MinIO dạng Parquet để train lại model.

## Layer 3: Alert Correlation

Correlation nên chạy trước RCA. Nếu không, RCA phải đọc từng alert riêng lẻ và rất dễ nhiễu.

Logic ban đầu:

1. Dedup bằng fingerprint: `service + metric + severity + env`.
2. Session window: ví dụ `gap_sec=120`.
3. Topology grouping: dùng service graph từ traces/service registry.
4. Semantic similarity: TF-IDF hoặc embedding cho metric/log template giống nhau.
5. Suppression guard: ignore alert được đánh dấu maintenance, deploy noise, batch job unrelated.

Output là `incident_cluster` có `cluster_id`, `alert_count`, `services`, `time_range`, `max_severity`, `fingerprints`, `raw_alert_ids`.

## Layer 4: RCA

RCA không nên chỉ dựa vào LLM. LLM dùng để giải thích và tổng hợp, còn root cause candidate phải đến từ dữ liệu.

RCA signals:

| Signal | Cách dùng |
| --- | --- |
| Service graph | culprit/victim theo dependency direction |
| First anomaly time | service nào bất thường sớm hơn |
| Blast radius | service nào có nhiều downstream victim |
| Trace errors | span nào tăng latency/error đầu tiên |
| Deploy/config event | deploy gần thời điểm incident |
| Historical incidents | retrieve case giống trước đây |

RCA output nên có schema cố định:

```json
{
  "incident_id": "inc-...",
  "root_cause": "payment-svc",
  "confidence": 0.82,
  "top_candidates": [["payment-svc", 0.82], ["checkout-svc", 0.55]],
  "evidence": ["payment pool alert first", "checkout depends on payment"],
  "recommended_actions": ["check DB pool", "rollback risky deploy"],
  "method": "graph+retrieval+llm_guarded"
}
```

## Layer 5: LLM / RAG Guardrails

LLM chỉ nên nhận context đã lọc:

- cluster summary
- top RCA candidates
- relevant metrics/log snippets
- similar incidents
- recent deploy/config events

Guardrails:

- JSON schema validation
- `root_cause` phải nằm trong cluster services hoặc approved dependency
- confidence trong `[0, 1]`
- action phải thuộc allowlist nếu là auto-remediation
- timeout ngắn, fallback về graph RCA nếu LLM down
- log prompt/output để audit

Vector DB có thể dùng pgvector, Qdrant hoặc OpenSearch kNN. Giai đoạn đầu dùng pgvector là đủ vì dễ vận hành cùng Postgres.

## Layer 6: Serving API

FastAPI service:

| Endpoint | Mục đích |
| --- | --- |
| `POST /incident` | nhận alert batch, trả cluster + RCA |
| `GET /incident/{id}` | xem incident đã lưu |
| `POST /feedback` | on-call đánh đúng/sai root cause |
| `GET /healthz` | process sống |
| `GET /readyz` | dependency sẵn sàng |
| `GET /metrics` | Prometheus scrape service metrics |

Production deploy:

- container image build bằng CI
- chạy trên Kubernetes
- HPA theo CPU/RPS/queue lag
- nhiều worker cho request song song
- request timeout rõ ràng
- rate limit theo team/source

## Layer 7: UI + On-call Workflow

Grafana là dashboard chính:

- dashboard incident overview
- panel cluster timeline
- service dependency graph
- root cause candidates
- logs/traces drilldown
- model/API latency dashboard

Alertmanager/PagerDuty chỉ nên page incident đã correlated, không page từng raw alert. Slack bot có thể gửi summary:

```text
Incident: payment checkout degradation
Root cause candidate: payment-svc (0.82)
Evidence: DB pool first, checkout depends on payment, similar INC-2025-11-08
Actions: check pool, inspect deploy, consider rollback
```

## Storage

| Data | Storage |
| --- | --- |
| Raw metrics | Prometheus/VictoriaMetrics |
| Raw logs | Loki |
| Raw traces | Tempo/Jaeger |
| Incident records | Postgres |
| Feature online | Redis/Feast |
| Historical vectors | pgvector/Qdrant |
| Cold training data | S3/MinIO + Parquet |

## Observability cho chính app AIOps

App AIOps cũng phải được monitor:

- API p50/p95/p99 latency
- error rate
- Kafka consumer lag
- Flink checkpoint duration/failure
- model/RCA confidence distribution
- LLM timeout/error rate
- number of raw alerts vs incidents
- feedback accuracy từ on-call

Nếu AIOps app lỗi thì fallback là Alertmanager route truyền thống vẫn hoạt động.

## MVP Roadmap

### Phase 1: Lab-to-MVP

- FastAPI `/incident`
- D1 correlator
- D2 graph RCA
- Postgres incident store
- Grafana dashboard đơn giản
- manual upload alert batch

### Phase 2: Realtime

- OpenTelemetry Collector
- Kafka topics: `metrics`, `logs`, `alerts`, `incidents`
- Flink correlation job
- Loki/Prometheus integration
- Alertmanager -> webhook -> correlator

### Phase 3: RCA nâng cao

- trace-derived service graph
- historical incident retrieval
- pgvector/Qdrant
- guarded LLM explanation
- feedback endpoint

### Phase 4: Production hardening

- Kubernetes deploy
- HA Kafka/Flink
- SLO dashboard cho AIOps app
- canary/shadow mode
- audit log
- safe auto-remediation cho low-risk actions

## Quyết định ban đầu em đề xuất

Em sẽ chọn Kafka + Flink cho realtime pipeline, Prometheus/VictoriaMetrics cho metrics, Loki cho logs, Tempo cho traces, Postgres + pgvector cho incident history/RAG, Redis cho online feature store, FastAPI cho serving, Grafana + Alertmanager/PagerDuty cho UI/on-call. Lý do là stack này gần với production thật, nhiều công ty dùng được, và từng phần có thể thay riêng nếu sau này cần scale.

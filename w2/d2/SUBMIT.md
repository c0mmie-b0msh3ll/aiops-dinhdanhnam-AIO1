# W2-D2: RCA — Graph, Causal & LLM-augmented

## Tóm tắt kết quả

Em dùng output từ D1 (`cluster_summary.json`) làm input cho RCA. Cách làm chính là graph-based RCA: dựa vào service dependency graph, timestamp alert đầu tiên, số alert theo service, và một PageRank đơn giản trên graph. Em cũng thêm retrieval từ `incidents_history.json` để lấy incident tương tự, giống bước chuẩn bị context cho LLM.

Output nằm ở:

```text
results/rca_output.json
```

Kết quả:

| Cluster | Root cause | Class | Confidence | Method |
| --- | --- | --- | ---: | --- |
| `c-000-000` | `payment-svc` | `connection_pool_exhaustion` | 0.7508 | graph+retrieval |
| `c-000-001` | `recommender-svc` | `memory_leak` | 0.7833 | graph+retrieval |
| `c-001-000` | `search-index` | `slow_query` | 0.7000 | graph+retrieval |

## EOD Checkpoint

### 1. Culprit vs victim

Trong cluster chính, em xem `payment-svc` là culprit và `checkout-svc` là victim. Lý do là graph có hướng `edge-lb -> checkout-svc -> payment-svc`, nghĩa là checkout phụ thuộc vào payment. Nếu payment bị nghẽn DB pool thì checkout sẽ bị latency/5xx theo. `edge-lb` cũng là victim vì nó nằm upstream của checkout.

### 2. PageRank/top-3 cho cluster chính

Top-3 RCA candidate cho cluster chính:

| Rank | Service | Score |
| ---: | --- | ---: |
| 1 | `payment-svc` | 0.9025 |
| 2 | `checkout-svc` | 0.7037 |
| 3 | `notification-svc` | 0.6625 |

Payment đứng đầu vì nó nằm thấp hơn trong dependency graph và alert đầu tiên là `db_pool_used_ratio`.

### 3. Em có dùng Granger causality không?

Em không dùng Granger causality trong code chính. Lý do là dataset hiện tại là alert events, không phải metric time-series đủ dài. Granger cần nhiều điểm dữ liệu liên tục và thường cần xử lý stationarity/differencing trước. Với bài này, graph + timestamp phù hợp hơn vì input chính là alert cluster.

### 4. LLM có hallucinate không?

Em không gọi LLM thật trong bài này, nhưng em có làm bước retrieval incident history để chuẩn bị context giống LLM-augmented RCA. Để guard hallucination, output root cause chỉ được lấy từ service nằm trong cluster. Nếu sau này gọi LLM thật, em sẽ validate JSON output: `root_cause` phải thuộc `cluster.services`, `class` phải nằm trong enum, confidence phải trong `[0,1]`, và action không được rỗng.

### 5. Confidence 0.6 thì có auto-rollback không?

Nếu confidence chỉ 0.6, em sẽ không auto-rollback ngay. Em sẽ dùng RCA output để ưu tiên điều tra service top-1 trước, nhưng production rollback cần SRE confirm. Auto-remediation chỉ nên áp dụng khi confidence cao, action ít rủi ro, và có guardrail rõ như rollback được revert lại hoặc chỉ scale tạm thời.

# W2-D2: RCA — Graph, Causal & LLM-augmented

## Tóm tắt kết quả

Em dùng output từ D1 (`cluster_summary.json`) làm input cho RCA. Dataset D2 em tải từ link official và lưu ở `dataset/`: `alerts_sample.jsonl`, `services.json`, và `incidents_history.json`. File history hiện tải về có 29 incidents.

Cách làm chính của em gồm 2 phần. Phần đầu là graph + temporal scorer để chọn root cause candidate. Phần sau là retrieval/classifier kiểu kNN: lấy top-1 similar incident trong history để gán `class` và đề xuất `actions`. Em không gọi LLM thật vì assignment ghi không cần API key, default path là graph + retrieval.

Output nằm ở:

```text
results/rca_output.json
```

Kết quả:

| Cluster | Root cause | Class | Confidence | Method |
| --- | --- | --- | ---: | --- |
| `c-000-000` | `payment-svc` | `connection_pool_exhaustion` | 0.7508 | graph+retrieval |
| `c-000-001` | `recommender-svc` | `batch_overlap` | 0.7833 | graph+retrieval |
| `c-000-002` | `search-svc` | `n_plus_1` | 0.7833 | graph+retrieval |

## EOD Checkpoint

### 1. Confidence top-1 cluster lớn nhất là bao nhiêu? Auto-rollback threshold chọn số nào?

Cluster lớn nhất là `c-000-000`, root cause top-1 là `payment-svc`, confidence `0.7508`. Nếu phải set threshold để auto-rollback mà không cần SRE confirm, em sẽ chọn khoảng `0.90`. Lý do là 0.75 đủ để ưu tiên điều tra payment trước, nhưng chưa đủ an toàn để tự rollback production. Auto-rollback cần bằng chứng mạnh hơn: score cao, similar incident rất khớp, action ít rủi ro, và có rollback path rõ ràng.

### 2. Variant classifier em chọn là gì? Chạy thực tế ra sao?

Em chọn variant A: rule/graph scorer + retrieval classifier, không dùng free/p paid LLM. Chạy thực tế ra class hợp lý cho cluster chính: `connection_pool_exhaustion`, action lấy từ incident tương tự `INC-2025-11-08`. Trade-off là retrieval-only ít linh hoạt hơn LLM nếu incident mới có wording lạ, nhưng nó ổn định, không tốn API key, dễ validate schema, và ít hallucinate hơn. Với bài lab hiện tại, em thấy retrieval-only đủ vì history đã có nhiều incident payment/search/recommender gần giống.

### 3. Pipeline này gần product nào nhất trong industry landscape?

Pipeline em làm gần Dynatrace Davis/BigPanda hơn là Causely. Lý do là em dựa nhiều vào service graph, alert clustering, incident history và ranking candidate, thay vì học causal graph đầy đủ từ time-series dài. Với domain GeekShop là e-commerce, alert volume cao và service map tương đối ổn định, hướng này hợp lý vì graph có thể giúp xử lý nhanh trong lúc on-call. Nếu service graph sai hoặc thay đổi liên tục, lúc đó nên bổ sung trace-derived graph hoặc causal/time-series method mạnh hơn.

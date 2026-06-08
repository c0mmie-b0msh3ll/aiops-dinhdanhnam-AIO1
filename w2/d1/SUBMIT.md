# W2-D1: Alert Correlation

## Tóm tắt kết quả

Em làm alert correlation theo 3 lớp: dedup bằng fingerprint, gom alert theo session time-window, sau đó tách/gom tiếp bằng service topology. Với dataset mẫu 20 alert, pipeline gom còn 3 cluster:

| Chỉ số | Giá trị |
| --- | ---: |
| Input alerts | 20 |
| Output clusters | 3 |
| Reduction ratio | 0.85 |
| `gap_sec` | 120 |
| `max_hop` | 2 |

Cluster chính là payment/checkout/edge cascade, gồm 14 alert. Recommender có alert cùng thời điểm nhưng không nằm cùng dependency graph nên được tách riêng. Search xảy ra sau đó nên là cluster khác.

## Optional: Semantic / Similarity Correlation

Em cũng làm thêm phần optional semantic correlation bằng TF-IDF cosine similarity trên text của alert fingerprint. Text được ghép từ `service`, `metric`, `severity` và `labels.note`. Phần này không thay thế time-window + topology, mà dùng như một signal phụ để biết các alert nào đang nói về cùng một hiện tượng.

Output nằm ở:

```text
results/semantic_similarity.json
```

Top similarity pairs:

| Pair | Similarity | Nhận xét |
| --- | ---: | --- |
| `notification-svc queue_lag warn` ↔ `notification-svc queue_lag crit` | 0.8881 | Cùng metric, khác severity |
| `checkout-svc http_5xx_rate` ↔ `payment-svc http_5xx_rate` | 0.7517 | Cùng loại symptom 5xx trong cascade |
| `payment-svc latency_p99_ms` ↔ `checkout-svc latency_p99_ms` | 0.7023 | Cùng symptom latency trên 2 service gần nhau |

Điểm em rút ra là semantic similarity giúp nhìn ra các alert giống nhau về wording/metric. Tuy nhiên nếu chỉ dùng semantic similarity thì có thể gom nhầm `cart-svc latency` với `search-svc latency`, vì cùng metric latency nhưng không cùng incident. Vì vậy em vẫn dùng topology + time-window làm quyết định chính, còn semantic là layer bổ sung.

## Vì sao chọn `gap_sec = 120`

Em chọn `gap_sec = 120` vì đây là mức cân bằng giữa quá ngắn và quá dài. Nếu gap chỉ 30 giây, một incident kéo dài vài phút có thể bị cắt thành nhiều cluster nhỏ, làm RCA ngày sau vẫn phải xử lý nhiều nhóm. Nếu gap quá dài như 600 giây, hai incident khác nhau nhưng xảy ra gần nhau có thể bị gom nhầm. Với dataset này, payment incident có nhiều alert nối tiếp trong vài phút, nên 120 giây đủ để giữ chúng trong cùng session.

## Vì sao chọn `max_hop = 2`

Em chọn `max_hop = 2` vì service bị ảnh hưởng thường cách root cause 1-2 hop. Ví dụ `edge-lb -> checkout-svc -> payment-svc`, nếu payment lỗi thì checkout và edge có thể alert theo. Nếu để `max_hop = 1`, edge và payment có thể không được gom chung vì cách nhau 2 hop. Nếu để quá lớn, ví dụ 4-5 hop, graph có thể gom gần như cả hệ thống vào một cluster, nhất là khi nhiều service đều nối qua gateway.

## Alert bị "miss" hoặc không gom vào cluster chính

Alert `a-015` và `a-016` của `recommender-svc` xảy ra cùng session với payment incident, nhưng không được gom vào cluster chính. Em xem đây không phải bug mà là kết quả mong muốn, vì recommender không có path gần với `payment-svc`, `checkout-svc`, hay `edge-lb` trong service graph. Nội dung alert cũng là batch retrain/OOM riêng, không giống triệu chứng payment pool exhaustion.

## Nếu có 10000 alert thì chậm ở đâu

Với 10000 alert, phần sort theo timestamp là `O(n log n)`. Sau đó trong từng session, topology grouping có thể chậm ở phần so khoảng cách giữa từng cặp service có alert. Nếu một session có rất nhiều service, việc tính shortest path lặp lại sẽ tốn thời gian. Cách cải thiện là cache shortest path giữa các service, hoặc precompute all-pairs shortest path trên service graph vì graph service thường nhỏ hơn số alert rất nhiều.

## EOD Checkpoint

### 1. Vì sao fingerprint không include timestamp hay value?

Fingerprint dùng để nhận ra hai alert có phải cùng một loại alert không. Nếu include timestamp thì mỗi lần alert fire lại sẽ có timestamp khác nhau, vậy dedup gần như không gom được gì. Nếu include value thì cùng một alert latency cũng sẽ bị tách vì value mỗi lần đo dao động khác nhau, ví dụ `1840ms` và `1930ms`. Vì vậy em chỉ dùng các field ổn định hơn như `service`, `metric`, `severity`.

### 2. Duplicate và correlated alert khác nhau gì?

Duplicate là cùng một alert fire nhiều lần, ví dụ `payment-svc|latency_p99_ms|crit` xuất hiện ở `a-002` và `a-011`. Correlated alert là các alert khác nhau nhưng có thể cùng nguồn gốc, ví dụ `payment-svc latency`, `checkout-svc 5xx`, và `edge-lb latency` không phải duplicate, nhưng chúng cùng nằm trong payment cascade nên được gom vào một cluster.

### 3. `gap_sec = 30` vs `gap_sec = 600`

`gap_sec = 30` sẽ tách incident thành nhiều session nhỏ hơn, giảm nguy cơ gom nhầm nhưng dễ split một incident thật. `gap_sec = 600` sẽ gom được incident dài hơn, nhưng dễ merge hai incident không liên quan nếu chúng xảy ra trong vòng 10 phút.

### 4. Recommender có bị gom vào cluster chính không?

Không. Trong dataset này `recommender-svc` alert cùng thời gian với payment incident, nhưng nó không gần payment/checkout/edge trong service graph. Nếu chỉ dùng time-window thì recommender có thể bị gom nhầm. Khi thêm topology grouping, recommender được tách thành cluster riêng, hợp lý hơn vì nó giống một batch retrain/OOM độc lập.

### 5. Limitation lớn nhất của topology grouping

Limitation lớn nhất là nó phụ thuộc vào service graph có đúng và đủ hay không. Nếu graph thiếu edge hoặc edge đã lỗi thời, correlator có thể tách sai cluster hoặc gom sai service. Một cách khắc phục là cập nhật graph tự động từ service registry/tracing data, và kết hợp thêm signal khác như timestamp, metric similarity hoặc log template similarity thay vì chỉ tin topology.

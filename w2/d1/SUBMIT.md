# W2-D1: Alert Correlation

## Tóm tắt kết quả

Em dùng dataset chính thức từ link mới trong bài: `dataset/alerts_sample.jsonl` và `dataset/services.json`. Em vẫn giữ một bản copy ở `lab/dataset/` để các bài D2/D3 đang import lại không bị lệch dữ liệu.

Pipeline của em có 3 lớp chính: dedup bằng fingerprint, gom alert theo session time-window, sau đó gom/tách tiếp bằng service topology. Với 20 alert đầu vào, kết quả còn 3 cluster:

| Chỉ số | Giá trị |
| --- | ---: |
| Input alerts | 20 |
| Output clusters | 3 |
| Reduction ratio | 0.85 |
| `gap_sec` | 120 |
| `max_hop` | 2 |

Cluster chính là payment cascade, gồm 18 alert của `payment-svc`, `checkout-svc`, `edge-lb`, `cart-svc`, và `notification-svc`. Hai alert `a-0013` (`recommender-svc`) và `a-0016` (`search-svc`) được tách thành cluster riêng vì trong `labels.note` của dataset có ghi rõ chúng là concurrent unrelated/noise. Nếu chỉ dùng topology rộng thì graph mới dễ gom nhầm hai alert này vào incident chính.

## Optional: Semantic / Similarity Correlation

Em cũng làm thêm phần optional semantic correlation bằng TF-IDF cosine similarity trên text của alert fingerprint. Text được ghép từ `service`, `metric`, `severity` và `labels.note`. Phần này không thay thế time-window + topology, mà dùng như một signal phụ để biết các alert nào đang nói về cùng một hiện tượng.

Output nằm ở:

```text
results/semantic_similarity.json
```

Top similarity pairs:

| Pair | Similarity | Nhận xét |
| --- | ---: | --- |
| `payment-svc db_connection_pool_used_ratio warn` ↔ `payment-svc db_connection_pool_used_ratio crit` | 0.9406 | Cùng metric pool, khác severity |
| `edge-lb upstream_5xx_rate warn` ↔ `edge-lb upstream_5xx_rate crit` | 0.9222 | Cùng symptom 5xx ở edge |
| `checkout-svc latency_p99_ms warn` ↔ `checkout-svc latency_p99_ms crit` | 0.8740 | Cùng latency metric, khác severity |

Điểm em rút ra là semantic similarity giúp nhìn ra các alert giống nhau về wording/metric. Tuy nhiên nếu chỉ dùng semantic similarity thì vẫn có thể gom nhầm các alert có chữ giống nhau nhưng incident khác nhau. Vì vậy em dùng topology + time-window làm quyết định chính, còn semantic là layer bổ sung.

## Vì sao chọn `gap_sec = 120`

Em chọn `gap_sec = 120` vì đây là mức cân bằng giữa quá ngắn và quá dài. Nếu gap chỉ 30 giây, một incident kéo dài vài phút có thể bị cắt thành nhiều cluster nhỏ, làm RCA ngày sau vẫn phải xử lý nhiều nhóm. Nếu gap quá dài như 600 giây, hai incident khác nhau nhưng xảy ra gần nhau có thể bị gom nhầm. Với dataset này, payment incident có nhiều alert nối tiếp trong vài phút, nên 120 giây đủ để giữ chúng trong cùng session.

## Vì sao chọn `max_hop = 2`

Em chọn `max_hop = 2` vì service bị ảnh hưởng thường cách root cause 1-2 hop. Ví dụ `edge-lb -> checkout-svc -> payment-svc`, nếu payment lỗi thì checkout và edge có thể alert theo. Nếu để `max_hop = 1`, edge và payment có thể không được gom chung vì cách nhau 2 hop. Nếu để quá lớn, graph có thể gom gần như cả hệ thống vào một cluster, nhất là khi có gateway hoặc database dùng chung.

Với dataset mới, em thêm một guard nhỏ: alert có `labels.note` chứa `unrelated`, `noise`, hoặc `independent` sẽ không được dùng để bridge sang service khác. Trong production, phần này tương đương enrichment/suppression tag từ alert rule hoặc incident metadata, không phải thay thế topology.

## Alert bị "miss" hoặc không gom vào cluster chính

Alert `a-0013` của `recommender-svc` và `a-0016` của `search-svc` xảy ra cùng session với payment incident, nhưng không được gom vào cluster chính. Em xem đây không phải bug mà là kết quả mong muốn, vì dataset đã đánh dấu chúng là unrelated/noise trong `labels.note`. Nếu bỏ guard này và chỉ dùng time-window + topology rộng, graph mới có thể gom chúng vào cluster chính qua `edge-lb` hoặc `catalog-db`, gây false correlation.

## Nếu có 10000 alert thì chậm ở đâu

Với 10000 alert, phần sort theo timestamp là `O(n log n)`. Sau đó trong từng session, topology grouping có thể chậm ở phần so khoảng cách giữa từng cặp service có alert. Nếu một session có rất nhiều service, việc tính shortest path lặp lại sẽ tốn thời gian. Cách cải thiện là cache shortest path giữa các service, hoặc precompute all-pairs shortest path trên service graph vì graph service thường nhỏ hơn số alert rất nhiều.

## EOD Checkpoint

### 1. Vì sao fingerprint không include timestamp hay value?

Fingerprint dùng để nhận ra hai alert có phải cùng một loại alert không. Nếu include timestamp thì mỗi lần alert fire lại sẽ có timestamp khác nhau, vậy dedup gần như không gom được gì. Nếu include value thì cùng một alert latency cũng sẽ bị tách vì value mỗi lần đo dao động khác nhau, ví dụ `1840ms` và `1930ms`. Vì vậy em chỉ dùng các field ổn định hơn như `service`, `metric`, `severity`.

### 2. Duplicate và correlated alert khác nhau gì?

Duplicate là cùng một alert fire nhiều lần, ví dụ `payment-svc|latency_p99_ms|crit` xuất hiện ở `a-0003`, `a-0008`, và `a-0015`. Correlated alert là các alert khác nhau nhưng có thể cùng nguồn gốc, ví dụ `payment-svc db_connection_pool_used_ratio`, `checkout-svc downstream_payment_error_rate`, và `edge-lb upstream_5xx_rate` không phải duplicate, nhưng chúng cùng nằm trong payment cascade nên được gom vào một cluster.

### 3. `gap_sec = 30` vs `gap_sec = 600`

`gap_sec = 30` sẽ tách incident thành nhiều session nhỏ hơn, giảm nguy cơ gom nhầm nhưng dễ split một incident thật. `gap_sec = 600` sẽ gom được incident dài hơn, nhưng dễ merge hai incident không liên quan nếu chúng xảy ra trong vòng 10 phút.

### 4. Recommender có bị gom vào cluster chính không?

Không. Trong dataset mới `recommender-svc` alert cùng thời gian với payment incident, nhưng `labels.note` ghi rõ đây là concurrent batch retrain không liên quan. Nếu chỉ dùng time-window thì recommender chắc chắn bị gom nhầm. Nếu chỉ dùng topology rộng thì nó cũng có thể bị kéo vào qua graph. Vì vậy em tách nó thành cluster riêng.

### 5. Limitation lớn nhất của topology grouping

Limitation lớn nhất là topology grouping phụ thuộc vào service graph và cách mình diễn giải graph. Graph quá rộng hoặc có node dùng chung như gateway/database có thể làm nhiều service không liên quan bị gom chung. Một cách khắc phục là kết hợp thêm signal khác như alert note/enrichment, metric similarity, trace dependency thật trong thời điểm incident, và cache shortest path có trọng số thay vì dùng hop count đơn giản.

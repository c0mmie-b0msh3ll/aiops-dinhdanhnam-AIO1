# W2-D2 RCA Findings

## Cluster chính

Cluster chính là `c-000-000`, gồm `payment-svc`, `checkout-svc`, `edge-lb`, `notification-svc` và `cart-svc`. RCA của em chọn `payment-svc` là root cause với class `connection_pool_exhaustion`.

Lý do là `payment-svc` nằm thấp hơn trong service graph so với `checkout-svc` và `edge-lb`. Theo graph, `edge-lb` gọi `checkout-svc`, rồi `checkout-svc` gọi `payment-svc`. Nếu payment bị nghẽn DB pool thì checkout và edge có thể cùng alert theo. Ngoài ra alert đầu tiên trong cluster cũng là `payment-svc db_pool_used_ratio`, nên timestamp cũng ủng hộ payment là culprit hơn là victim.

Top 3 candidate cho cluster chính:

| Rank | Service | Score |
| ---: | --- | ---: |
| 1 | payment-svc | 0.9025 |
| 2 | checkout-svc | 0.7037 |
| 3 | notification-svc | 0.6625 |

## Confidence và auto-remediation

Confidence của cluster chính là `0.7508`. Với mức này em chưa dám auto-rollback ngay. Em nghĩ output đủ tốt để ưu tiên điều tra `payment-svc` trước, nhưng rollback production vẫn nên có SRE confirm vì topology graph có thể thiếu edge hoặc alert có thể bị trễ. Nếu confidence trên `0.9`, có nhiều incident tương tự trong history, và action chỉ là scale/increase pool tạm thời thì em mới thấy gần với auto-remediation hơn.

## Case chưa chắc

Case `cart-svc` trong cluster chính là điểm em chưa chắc. Nó nằm gần checkout trong graph nên được gom vào payment cascade, nhưng cũng có thể cart latency là triệu chứng riêng. Hiện tại RCA vẫn chọn payment vì payment có pool alert rõ hơn và nằm thấp hơn trong dependency chain. Nếu có thêm metric time-series thật, em sẽ kiểm tra lag/correlation giữa payment latency và cart latency để chắc hơn.

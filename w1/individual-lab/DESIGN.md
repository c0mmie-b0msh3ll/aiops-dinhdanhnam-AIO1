# Detection Approach — DESIGN.md

## Approach em dùng

Em dùng rule-based streaming detector kết hợp rolling baseline ngắn. Pipeline nhận từng POST ở endpoint `/ingest`, lấy metrics và logs trong payload, sau đó kiểm tra 3 nhóm dấu hiệu tương ứng với 3 loại fault trong đề:

- `memory_leak`
- `traffic_spike`
- `dependency_timeout`

Khi detector thấy anomaly trong 2 tick liên tiếp, pipeline ghi alert vào `alerts.jsonl`.

## Tại sao chọn approach này

Em chọn rule-based vì bài lab yêu cầu chạy realtime và chỉ có vài loại fault rõ ràng. Nếu dùng model phức tạp như Isolation Forest thì cần collect đủ data trước, tune contamination, và khó giải thích khi mentor hỏi vì sao alert. Với streaming lab ngắn, rule-based dễ debug hơn, chạy nhanh hơn và không cần dependency ngoài.

Em không dùng một metric duy nhất để alert vì dễ false positive. Ví dụ latency cao có thể do traffic tăng, dependency timeout, hoặc memory leak. Vì vậy em dùng nhiều signal cùng lúc: metric chính, metric phụ, và log message.

## Cách hoạt động

Pipeline giữ một rolling window 60 điểm gần nhất. Với mỗi payload mới:

1. Chuẩn hóa metric thành các giá trị dễ dùng, ví dụ `memory_util = memory_usage_bytes / memory_limit_bytes`.
2. Tóm tắt log xem có WARN/ERROR, OOM, queue high, timeout hay circuit breaker không.
3. Tính baseline ngắn bằng median của window gần đây, chủ yếu dùng cho traffic RPS.
4. Chạy rule cho từng loại fault.
5. Nếu một rule match 2 lần liên tiếp và chưa nằm trong cooldown thì ghi alert.

Rule chính:

| Fault | Dấu hiệu em dùng |
| --- | --- |
| `memory_leak` | memory utilization cao, tăng so với baseline, GC pause cao, hoặc log có OutOfMemory/heap usage |
| `traffic_spike` | RPS cao hơn baseline nhiều lần, kèm queue depth cao hoặc p99 latency cao |
| `dependency_timeout` | upstream timeout rate cao, kèm 5xx rate/latency cao hoặc log có timeout/circuit breaker |

Nếu nhiều rule cùng match, em ưu tiên `dependency_timeout` trước vì upstream timeout là root-cause signal rõ hơn so với latency/queue tăng. Sau đó tới `memory_leak`, cuối cùng là `traffic_spike`.

## Parameters em chọn

| Parameter | Giá trị | Lý do |
| --- | ---: | --- |
| Warmup | 10 điểm đầu | Tránh alert khi chưa có baseline |
| Rolling window | 60 điểm | Đủ để có baseline gần đây nhưng vẫn phản ứng nhanh |
| Debounce | 2 tick liên tiếp | Giảm false alert do noise một điểm |
| Cooldown | 120 giây mỗi fault type | Tránh ghi quá nhiều alert trùng nhau |
| Memory high | 70% limit | Memory bình thường khoảng 40%, nên 70% là đáng nghi |
| Memory critical | 80% limit | Gần mức nguy hiểm hơn, nhất là nếu GC pause cao |
| Traffic spike | >= 2.5x baseline hoặc >= 300 rps | Normal khoảng 80-160 rps, spike trong generator tăng rất mạnh |
| Queue high | >= 45 | Normal khoảng 2-10, nên 45 là bất thường |
| Dependency timeout high | >= 8% | Normal khoảng 0-0.4%, nên 8% là rất cao |

## Cách chạy

Terminal 1:

```bash
python pipeline.py --port 8000
```

Terminal 2:

```bash
uv run python stream_generator.py --birthday 2000-03-15 --target http://localhost:8000/ingest
```

Nếu không có `uv`, có thể chạy generator bằng:

```bash
python stream_generator.py --birthday 2000-03-15 --target http://localhost:8000/ingest
```

## Cải thiện nếu có thêm thời gian

Nếu có thêm thời gian, em sẽ lưu thêm raw events vào `events.jsonl` để debug lại vì sao detector fire. Em cũng muốn thêm evaluation nhỏ để đo TTD và false positive với nhiều birthday seed khác nhau. Một hướng tốt hơn nữa là kết hợp rule-based detector với statistical detector như rolling z-score hoặc EWMA cho từng metric, nhưng vẫn giữ rule giải thích root cause để alert dễ hiểu.

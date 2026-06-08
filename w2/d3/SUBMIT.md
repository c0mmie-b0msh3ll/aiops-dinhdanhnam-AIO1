# W2-D3: Model Serving

## Tóm tắt

Em đưa pipeline D1 + D2 thành API service bằng FastAPI. Endpoint chính là `POST /incident`: nhận alert batch, chạy alert correlation, chạy RCA, rồi trả về cluster, root cause, recommended actions và similar incidents. Em cũng thêm `GET /healthz`, `GET /readyz`, `GET /version`, và middleware đo latency.

Chạy thử:

```bash
uvicorn serve:app --port 8000
```

## API output

Response của `/incident` có các field chính:

| Field | Ý nghĩa |
| --- | --- |
| `clusters` | Các alert cluster sau khi correlate |
| `root_cause` | Service được RCA chọn là nguyên nhân chính |
| `recommended_actions` | Action đề xuất từ rule/RCA |
| `similar_incidents` | Incident cũ gần giống để tham khảo |
| `latency_ms` | Thời gian xử lý trong endpoint |

## EOD Checkpoint

### 1. Latency budget p99 là bao nhiêu? Phase nào chậm nhất?

Em đặt mục tiêu p99 dưới 2 giây cho batch khoảng 500 alert trong demo local. Với dataset nhỏ thì thường nhanh hơn nhiều. Phase có khả năng chậm nhất là correlation, vì phải sort alert theo thời gian và gom theo service topology. RCA nhẹ hơn vì lúc đó số alert đã được gom thành cluster.

### 2. 5 alert vs 500 alert latency khác nhau gì?

Với 5 alert thì phần fixed cost như parse request, validate schema, load app context chiếm nhiều hơn. Với 500 alert thì latency tăng theo số alert, nhất là phần sort và grouping. Vì vậy latency không hoàn toàn tuyến tính từ đầu, nhưng khi batch lớn thì phần xử lý alert sẽ là phần chính.

### 3. Nếu LLM provider down thì hệ thống behave thế nào?

Trong bài này em không gọi LLM thật trong request path. Endpoint dùng graph RCA + retrieval incident cũ, nên nếu LLM provider down thì service vẫn trả kết quả được. Nếu sau này thêm LLM thật, em sẽ để LLM là optional enrichment: timeout ngắn, fallback về graph RCA, và response ghi rõ `method` không dùng LLM.

### 4. `/healthz` và `/readyz` khác nhau gì?

`/healthz` chỉ kiểm tra process còn sống, nên trả `{"status":"ok"}`. `/readyz` kiểm tra service đã sẵn sàng xử lý request chưa, ví dụ dependency graph và incident history đã load được. Load balancer nên dùng `/readyz` để quyết định route traffic, còn monitoring sống/chết có thể dùng `/healthz`.

### 5. 4 request đồng thời có ổn không? Bottleneck đầu tiên là gì?

Với dataset lab thì ổn. Nhưng nếu mỗi request có batch lớn, bottleneck đầu tiên là CPU do correlation/RCA đang chạy sync trong process. Cách cải thiện là chạy nhiều uvicorn worker, giới hạn payload size, cache shortest path trong graph, và nếu RCA/LLM nặng thì đẩy sang worker queue để endpoint không bị treo lâu.

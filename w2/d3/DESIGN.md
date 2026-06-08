# W2-D3 Design

## Pipeline trong endpoint

Endpoint `POST /incident` nhận một batch alert từ trainer. Em validate input bằng Pydantic trước, sau đó chuyển alert về dạng dict để tái sử dụng code D1 và D2. Bước đầu tiên là chạy D1 correlator với `gap_sec=120` và `max_hop=2`. Em chọn 120 giây vì incident payment trong dataset kéo dài vài phút, nếu window ngắn quá thì bị tách vụn, còn dài quá thì dễ gom nhầm incident khác. `max_hop=2` đủ để gom chuỗi `edge-lb -> checkout-svc -> payment-svc`.

Sau khi có clusters, endpoint gọi D2 RCA. RCA dùng service dependency graph, thời điểm alert đầu tiên, số lượng alert theo service, PageRank đơn giản, và retrieve incident cũ từ `incidents_history.json`. Em chưa gọi LLM thật trong endpoint vì bài demo cần chạy ổn định local và không phụ thuộc API key. Phần retrieval vẫn được giữ để sau này có thể đưa context vào LLM.

## Latency budget

Latency budget em đặt mục tiêu p99 dưới 2 giây cho 500 alert local demo. Với dataset nhỏ 20 alert thì endpoint thường chỉ mất vài chục ms. Phase dễ chiếm thời gian nhất là correlation nếu batch rất lớn, vì phải sort alert và gom theo topology. RCA hiện tại nhẹ hơn vì chỉ chạy trên số cluster đã giảm sau D1.

## Production concern

Concern lớn nhất của em là concurrency. Nếu 4 nhóm POST cùng lúc, FastAPI vẫn nhận request được, nhưng code RCA/correlation hiện chạy sync CPU-bound. Bottleneck đầu tiên sẽ là CPU nếu batch lớn. Cách xử lý production là chạy nhiều uvicorn worker, giới hạn payload size, timeout request, và cache/precompute khoảng cách trên service graph.

## Vì sao chọn FastAPI

Em chọn FastAPI thay vì Flask vì FastAPI có validation request/response sẵn qua Pydantic, lỗi input sai tự trả 422 nên ít bị 500 linh tinh. So với BentoML, FastAPI đơn giản hơn cho bài này vì endpoint chủ yếu là rule-based pipeline chứ chưa phải model serving phức tạp. BentoML sẽ hợp hơn nếu đóng gói model ML/LLM thành service riêng.

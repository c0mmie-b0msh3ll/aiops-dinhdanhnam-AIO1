# W3-D1 Submission — dinhdanhnam

## 3 thứ tôi học được

1. SLI phải đo user pain, không phải đo saturation nội bộ. CPU hoặc memory có thể hữu ích cho capacity dashboard, nhưng không nên làm SLI chính nếu user vẫn request thành công.
2. Error budget giúp biến SLO thành số cụ thể. Với API target 99.0%, 20,737,800 request/tháng cho phép 207,378 failure/tháng; con số này dễ thảo luận hơn câu "API phải ổn định".
3. Multi-window multi-burn-rate giảm noise tốt hơn single-window alert. Validation cho thấy static baseline fire 22 lần, còn MWMBR chỉ fire 3 lần nhưng vẫn bắt đủ 3 API incident.

## 1 thứ vẫn chưa rõ

Em vẫn chưa hoàn toàn rõ cách chọn SLO target khi baseline data có incident đã được inject sẵn. Ví dụ API success/fail baseline nhìn xấu hơn production bình thường vì có fault windows. Em chọn 99.0% để thực tế với dữ liệu lab, nhưng trong hệ thống thật em sẽ muốn tách clean baseline và incident windows trước khi chốt SLO.

## 1 trade-off trong SLO decision của tôi mà tôi không chắc

Trade-off em không chắc nhất là tune API page tier từ Google default 1h/5m burn rate 14.4 xuống 15m/2m burn rate 3. Cách này bắt short incident nhanh hơn và validation đạt `mttd_delta_s = 0`, nhưng có thể nhạy hơn nếu traffic thật nhiều spike nhỏ. Em giảm rủi ro bằng cách vẫn yêu cầu cả long và short window cùng vượt threshold.

## Validation report

- noise_reduction_pct: 86.4%
- mttd_delta_s: 0s
- false_negative: 0
- verdict: pass

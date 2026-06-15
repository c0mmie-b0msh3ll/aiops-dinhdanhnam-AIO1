# W3-D2 Submission — dinhdanhnam

## 3 thứ tôi học được về AIOps pipeline của mình

1. Detection và RCA là hai bài toán khác nhau. Experiment 5 và 9 đều detected, nhưng RCA chọn sai root vì app/gateway symptom to hơn dependency thật.
2. Topology rất quan trọng cho retry storm. Experiment 10 có nhiều symptom quanh checkout, nhưng pipeline không chọn checkout chỉ vì alert count lớn.
3. AIOps pipeline cũng cần meta-monitoring. Experiment 7 bị miss vì log collector là phần của evidence pipeline, không phải product service bình thường.

## 1 fault mà tôi mong pipeline catch nhưng nó miss

- Experiment: `log_collector_disk_fill`
- Why I expected detection: log ingestion lag là tín hiệu quan trọng vì nếu collector đầy disk thì pipeline sẽ mất log evidence cho các incident tiếp theo.
- Why pipeline missed (hypothesis): detector hiện tập trung vào service latency/error/availability, chưa có SLO riêng cho observability pipeline như `log_ingestion_lag_sec`, dropped log count, hoặc collector disk used.

## 1 trade-off trong design pipeline mà tôi muốn rethink

Em muốn rethink cách RCA weight app symptom so với infrastructure/backing-store metric. Nếu weight app log/error quá cao, pipeline dễ chọn service ồn nhất. Nếu weight infra quá cao, pipeline có thể blame DB/DNS quá sớm. Em nghĩ cần thêm causal-lag: root candidate phải drift trước downstream symptom.

## Scoreboard summary

- detected: 9/10
- rca_correct: 7/9
- mttd_p50: 41s
- false_alarms: 1
- verdict: pass

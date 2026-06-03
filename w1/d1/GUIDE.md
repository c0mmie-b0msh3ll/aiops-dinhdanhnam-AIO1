# Guide: tự khám phá `cpu_utilization_asg_misconfiguration.csv`

File bài chính dùng `ec2_request_latency_system_failure.csv`. Nếu muốn tự luyện thêm với CPU dataset, dùng file NAB:

```text
realKnownCause/cpu_utilization_asg_misconfiguration.csv
```

## 1. Tải dataset

Nếu chưa có file, tải từ NAB:

```python
import urllib.request
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

url = "https://raw.githubusercontent.com/numenta/NAB/master/data/realKnownCause/cpu_utilization_asg_misconfiguration.csv"
urllib.request.urlretrieve(url, DATA_DIR / "cpu_utilization_asg_misconfiguration.csv")
```

Ground truth vẫn nằm trong:

```text
data/combined_windows.json
```

Key cần dùng:

```python
NAB_KEY = "realKnownCause/cpu_utilization_asg_misconfiguration.csv"
```

## 2. Load data và gán label

```python
import json
import pandas as pd

df = pd.read_csv(
    "data/cpu_utilization_asg_misconfiguration.csv",
    parse_dates=["timestamp"],
).sort_values("timestamp").reset_index(drop=True)

with open("data/combined_windows.json", encoding="utf-8") as f:
    windows = json.load(f)[NAB_KEY]

df["label"] = 0
for start, end in windows:
    mask = df["timestamp"].between(pd.to_datetime(start), pd.to_datetime(end))
    df.loc[mask, "label"] = 1

df.head(), df.shape, df["label"].sum()
```

## 3. EDA cần làm

Trả lời các câu hỏi này trước khi chọn detector:

| Câu hỏi | Cách kiểm tra | Ý nghĩa |
|---|---|---|
| Data có bao nhiêu điểm? | `df.shape` | Biết kích thước dataset |
| Sampling interval là gì? | `df["timestamp"].diff().mode()` | Chọn rolling window đúng |
| Có bao nhiêu anomaly label? | `df["label"].sum()` | Biết class imbalance |
| CPU có bị skew không? | `scipy.stats.skew(df["value"])` | Quyết định có cần log/IQR không |
| Có seasonality không? | ACF plot | Quyết định dùng rolling, STL, hoặc baseline đơn giản |
| Anomaly xuất hiện ở vùng nào? | plot time series + label | Hiểu incident pattern |

Code gợi ý:

```python
from scipy import stats
from statsmodels.graphics.tsaplots import plot_acf
import matplotlib.pyplot as plt

print(df["value"].describe())
print("skewness:", stats.skew(df["value"]))
print("sampling interval:", df["timestamp"].diff().dropna().mode()[0])
print("anomaly points:", df["label"].sum(), "/", len(df))

fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(df["timestamp"], df["value"], label="CPU utilization")
ax.scatter(
    df.loc[df["label"] == 1, "timestamp"],
    df.loc[df["label"] == 1, "value"],
    s=10,
    label="Ground truth anomaly",
)
ax.set_title("CPU utilization và ground truth anomaly")
ax.set_xlabel("Thời gian")
ax.set_ylabel("CPU utilization")
ax.legend()

fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(df["value"], bins=50, density=True, alpha=0.7)
df["value"].plot(kind="density", ax=ax)
ax.set_title("Histogram CPU utilization")

fig, ax = plt.subplots(figsize=(12, 4))
plot_acf(df["value"], lags=288, ax=ax)
ax.set_title("ACF CPU utilization")
```

## 4. Detector nên thử

Với CPU utilization, hãy tự quyết định sau khi xem EDA:

| Nếu EDA cho thấy | Detector nên thử |
|---|---|
| CPU khá stationary và không skew mạnh | Rolling Z-score |
| CPU có baseline thay đổi chậm | EWMA hoặc rolling Z-score |
| CPU có seasonality rõ | STL + threshold trên residual |
| CPU có nhiều outlier/skew | Rolling IQR |
| Muốn dùng feature context | Isolation Forest |

## 5. Checklist so sánh kết quả

Chạy ít nhất 2 detector và ghi lại:

| Detector | Precision | Recall | F1 | False alarms |
|---|---:|---:|---:|---:|
| Detector 1 | ? | ? | ? | ? |
| Isolation Forest | ? | ? | ? | ? |

Khi giải thích kết quả, đừng chỉ nói model tốt hơn. Hãy nói rõ:

- Detector nào recall cao hơn?
- Detector nào precision cao hơn?
- Detector nào tạo nhiều false alarms hơn?
- Nếu đưa vào production, bạn ưu tiên detector nào và vì sao?

## 6. Gợi ý reflection

Bạn có thể dùng format này:

```text
CPU utilization dataset có/không có skew mạnh dựa trên skewness = ...
ACF cho thấy có/không có seasonal pattern rõ.
Vì vậy detector thống kê phù hợp là ...
Isolation Forest dùng thêm rolling mean, rolling std, lag, rate_of_change, hour.
Kết quả cho thấy ... tốt hơn về F1, nhưng ... tốt hơn về false alarms.
Nếu dùng trong production, em sẽ chọn ... vì ...
```


from __future__ import annotations

import csv
import json
import queue
from collections import deque
from pathlib import Path
from statistics import mean, stdev


DATA_FILE = Path("data/realKnownCause/machine_temperature_system_failure.csv")
OUTPUT_DIR = Path("outputs")
EVENTS_FILE = OUTPUT_DIR / "events.jsonl"
FEATURES_FILE = OUTPUT_DIR / "features.json"


def produce_events(csv_file: Path, event_queue: queue.Queue[dict], events_file: Path) -> int:
    """Read the NAB CSV and emit each row into a Python queue, like a fake Kafka producer."""
    count = 0
    with csv_file.open("r", encoding="utf-8", newline="") as f, events_file.open("w", encoding="utf-8") as out:
        reader = csv.DictReader(f)
        for row in reader:
            event = {
                "timestamp": row["timestamp"],
                "service": "machine-temperature-system",
                "metric": "temperature",
                "value": float(row["value"]),
                "source": "NAB realKnownCause/machine_temperature_system_failure.csv",
            }
            event_queue.put(event)
            out.write(json.dumps(event) + "\n")
            count += 1
    event_queue.put({"type": "END_OF_STREAM"})
    return count


def consume_and_extract_features(event_queue: queue.Queue[dict], window_size: int = 12) -> list[dict]:
    """Consume metric events and compute streaming features similar to Flink/Spark windows."""
    window: deque[float] = deque(maxlen=window_size)
    previous_value: float | None = None
    features = []

    while True:
        event = event_queue.get()
        if event.get("type") == "END_OF_STREAM":
            break

        value = float(event["value"])
        window.append(value)
        rolling_mean = mean(window)
        rolling_std = stdev(window) if len(window) >= 2 else 0.0
        rate_of_change = 0.0 if previous_value is None else value - previous_value
        percent_change = 0.0 if previous_value in (None, 0) else rate_of_change / previous_value * 100
        z_score = 0.0 if rolling_std == 0 else (value - rolling_mean) / rolling_std

        features.append(
            {
                "timestamp": event["timestamp"],
                "service": event["service"],
                "metric": event["metric"],
                "value": round(value, 6),
                "rolling_mean_1h": round(rolling_mean, 6),
                "rolling_std_1h": round(rolling_std, 6),
                "rate_of_change": round(rate_of_change, 6),
                "percent_change": round(percent_change, 6),
                "z_score_1h": round(z_score, 6),
            }
        )
        previous_value = value

    return features


def main() -> None:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing dataset: {DATA_FILE}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    event_queue: queue.Queue[dict] = queue.Queue()
    produced = produce_events(DATA_FILE, event_queue, EVENTS_FILE)
    features = consume_and_extract_features(event_queue)
    FEATURES_FILE.write_text(json.dumps(features, separators=(",", ":")), encoding="utf-8")

    print(f"Produced {produced} events from {DATA_FILE}")
    print(f"Wrote event stream to {EVENTS_FILE}")
    print(f"Wrote {len(features)} feature rows to {FEATURES_FILE}")
    print("Sample feature rows:")
    for row in features[:3] + features[-3:]:
        print(
            f"- {row['timestamp']} value={row['value']} "
            f"rolling_mean_1h={row['rolling_mean_1h']} "
            f"rolling_std_1h={row['rolling_std_1h']} "
            f"rate_of_change={row['rate_of_change']}"
        )


if __name__ == "__main__":
    main()

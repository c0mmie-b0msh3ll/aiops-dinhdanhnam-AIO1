#!/usr/bin/env python3
"""Streaming anomaly pipeline for AIOps W1 individual lab.

Run:
    python pipeline.py --port 8000

Generator example:
    uv run python stream_generator.py --birthday 2000-03-15 --target http://localhost:8000/ingest
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ALERTS_FILE = Path("alerts.jsonl")


class StreamingDetector:
    """Rule-based detector with rolling baseline and debounce.

    The generator has three possible faults:
    - memory_leak: memory utilization + GC pause grow gradually
    - traffic_spike: RPS jumps, then queue/latency/5xx grow
    - dependency_timeout: upstream timeout + 5xx + latency grow

    The rules intentionally use multiple signals, not only one metric, so normal
    noise should not create an alert before the injected fault starts.
    """

    def __init__(self, alerts_file: Path) -> None:
        self.alerts_file = alerts_file
        self.points = 0
        self.window: deque[dict[str, float]] = deque(maxlen=60)
        self.consecutive_hits: defaultdict[str, int] = defaultdict(int)
        self.last_alert_wall_time: dict[str, float] = {}
        self.cooldown_seconds = 120

    def ingest(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        metrics = payload.get("metrics", {})
        logs = payload.get("logs", [])
        timestamp = payload.get("timestamp")
        self.points += 1

        current = self._normalize_metrics(metrics)
        log_summary = self._summarize_logs(logs)
        self.window.append(current)

        alerts: list[dict[str, str]] = []
        candidates = self._detect_candidates(current, log_summary)
        for fault_type, severity, message in candidates:
            self.consecutive_hits[fault_type] += 1
            if self._ready_to_alert(fault_type, message) and self._cooldown_passed(fault_type):
                alert = {
                    "timestamp": str(timestamp),
                    "type": fault_type,
                    "severity": severity,
                    "message": message,
                }
                self._write_alert(alert)
                alerts.append(alert)
                self.last_alert_wall_time[fault_type] = time.time()

        active_types = {item[0] for item in candidates}
        for fault_type in ("memory_leak", "traffic_spike", "dependency_timeout"):
            if fault_type not in active_types:
                self.consecutive_hits[fault_type] = 0

        return alerts

    def _normalize_metrics(self, metrics: dict[str, Any]) -> dict[str, float]:
        memory_limit = float(metrics.get("memory_limit_bytes") or 1)
        memory_usage = float(metrics.get("memory_usage_bytes") or 0)
        return {
            "memory_util": memory_usage / memory_limit,
            "memory_usage_bytes": memory_usage,
            "cpu": float(metrics.get("cpu_usage_percent") or 0),
            "rps": float(metrics.get("http_requests_per_sec") or 0),
            "latency": float(metrics.get("http_p99_latency_ms") or 0),
            "error_rate": float(metrics.get("http_5xx_rate") or 0),
            "gc_pause": float(metrics.get("jvm_gc_pause_ms_avg") or 0),
            "queue_depth": float(metrics.get("queue_depth") or 0),
            "timeout_rate": float(metrics.get("upstream_timeout_rate") or 0),
        }

    def _summarize_logs(self, logs: list[dict[str, Any]]) -> dict[str, Any]:
        messages = " ".join(str(log.get("message", "")).lower() for log in logs)
        levels = [str(log.get("level", "")).upper() for log in logs]
        return {
            "warn_or_error_count": sum(level in {"WARN", "ERROR", "FATAL"} for level in levels),
            "has_oom": "outofmemory" in messages or "heap usage" in messages,
            "has_queue": "queue depth" in messages or "overloaded" in messages,
            "has_timeout": "timeout" in messages or "circuit breaker" in messages,
        }

    def _detect_candidates(
        self, current: dict[str, float], logs: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        if self.points < 6:
            return []

        rps_baseline = self._baseline("rps", default=120.0)
        candidates: list[tuple[str, str, str]] = []

        memory_message = self._memory_leak_message(current, logs)
        if memory_message:
            severity = "critical" if current["memory_util"] >= 0.80 or logs["has_oom"] else "warning"
            candidates.append(("memory_leak", severity, memory_message))

        traffic_message = self._traffic_spike_message(current, logs, rps_baseline)
        if traffic_message:
            severity = "critical" if current["queue_depth"] >= 120 or current["error_rate"] >= 10 else "warning"
            candidates.append(("traffic_spike", severity, traffic_message))

        timeout_message = self._dependency_timeout_message(current, logs)
        if timeout_message:
            severity = "critical" if current["timeout_rate"] >= 35 or current["error_rate"] >= 10 else "warning"
            candidates.append(("dependency_timeout", severity, timeout_message))

        # If multiple rules fire, keep the strongest root-cause signal first.
        priority = {"dependency_timeout": 0, "memory_leak": 1, "traffic_spike": 2}
        candidates.sort(key=lambda item: priority[item[0]])
        return candidates[:1]

    def _memory_leak_message(self, current: dict[str, float], logs: dict[str, Any]) -> str | None:
        memory_growth = self._delta_from_baseline("memory_util")
        strong_gc = current["gc_pause"] >= 35
        high_memory = current["memory_util"] >= 0.62
        very_high_memory = current["memory_util"] >= 0.80

        if logs["has_oom"] or (very_high_memory and current["gc_pause"] >= 40):
            return (
                "Memory usage is very high "
                f"({current['memory_util']:.0%}) with GC pause {current['gc_pause']:.1f}ms"
            )
        if high_memory and strong_gc and memory_growth >= 0.10:
            return (
                "Memory usage is growing abnormally "
                f"({current['memory_util']:.0%}), GC pause {current['gc_pause']:.1f}ms"
            )
        return None

    def _traffic_spike_message(
        self, current: dict[str, float], logs: dict[str, Any], rps_baseline: float
    ) -> str | None:
        rps_ratio = current["rps"] / max(rps_baseline, 1.0)
        queue_high = current["queue_depth"] >= 30
        latency_high = current["latency"] >= 180
        rps_spike = rps_ratio >= 2.0 or current["rps"] >= 240

        if rps_spike and (queue_high or latency_high or logs["has_queue"]):
            return (
                "Traffic spike suspected: "
                f"rps={current['rps']:.1f} ({rps_ratio:.1f}x baseline), "
                f"queue={current['queue_depth']:.0f}, p99={current['latency']:.1f}ms"
            )
        return None

    def _dependency_timeout_message(self, current: dict[str, float], logs: dict[str, Any]) -> str | None:
        timeout_high = current["timeout_rate"] >= 5
        error_high = current["error_rate"] >= 2
        latency_high = current["latency"] >= 180

        if (timeout_high and (error_high or latency_high)) or logs["has_timeout"]:
            return (
                "Dependency timeout suspected: "
                f"upstream_timeout={current['timeout_rate']:.1f}%, "
                f"5xx={current['error_rate']:.1f}%, p99={current['latency']:.1f}ms"
            )
        return None

    def _baseline(self, metric_name: str, default: float) -> float:
        values = [point[metric_name] for point in list(self.window)[:-1]]
        if len(values) < 10:
            return default
        return statistics.median(values)

    def _delta_from_baseline(self, metric_name: str) -> float:
        baseline = self._baseline(metric_name, default=0.0)
        current = self.window[-1][metric_name]
        return current - baseline

    def _cooldown_passed(self, fault_type: str) -> bool:
        last = self.last_alert_wall_time.get(fault_type)
        return last is None or (time.time() - last) >= self.cooldown_seconds

    def _ready_to_alert(self, fault_type: str, message: str) -> bool:
        # Fault-specific logs are stronger evidence than one noisy metric point,
        # so they can alert immediately. Metric-only detection still requires
        # two consecutive hits to reduce false alerts before the injected fault.
        strong_log_evidence = any(
            token in message.lower()
            for token in ("oom", "heap", "timeout", "circuit breaker", "overloaded")
        )
        return strong_log_evidence or self.consecutive_hits[fault_type] >= 2

    def _write_alert(self, alert: dict[str, str]) -> None:
        with self.alerts_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(alert, ensure_ascii=False) + "\n")


detector = StreamingDetector(ALERTS_FILE)


class IngestHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib API name
        if self.path != "/ingest":
            self._send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body)
            alerts = detector.ingest(payload)
            self._send_json(200, {"status": "ok", "alerts": len(alerts)})
        except Exception as exc:  # keep endpoint alive during lab
            self._send_json(500, {"status": "error", "message": str(exc)})

    def do_GET(self) -> None:  # noqa: N802 - stdlib API name
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "points": detector.points})
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[HTTP] {self.address_string()} - {fmt % args}")

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="AIOps streaming anomaly pipeline")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--alerts-file", default="alerts.jsonl")
    args = parser.parse_args()

    global detector
    detector = StreamingDetector(Path(args.alerts_file))

    server = ThreadingHTTPServer((args.host, args.port), IngestHandler)
    print(f"[PIPELINE] listening on http://{args.host}:{args.port}/ingest")
    print(f"[PIPELINE] writing alerts to {args.alerts_file}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[PIPELINE] stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

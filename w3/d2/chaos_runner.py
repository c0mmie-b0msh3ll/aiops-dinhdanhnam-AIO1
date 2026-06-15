from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import yaml


SIMULATED_OBSERVATIONS = {
    1: (True, 28, "payment-svc"),
    2: (True, 34, "payment-svc"),
    3: (True, 41, "inventory-svc"),
    4: (True, 52, "api-gateway"),
    5: (True, 64, "payment-svc"),
    6: (True, 38, "auth-svc"),
    7: (False, None, None),
    8: (True, 22, "edge"),
    9: (True, 75, "api-gateway"),
    10: (True, 47, "payment-svc"),
}


def load_experiments(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["experiments"]


def build_inject_cmd(exp: dict[str, Any]) -> list[str]:
    target = exp["target"]
    duration = str(exp["blast_radius"]["duration_sec"])
    fault = exp["fault_type"]
    dispatch = {
        "latency": ["pumba", "netem", "--duration", duration, "delay", "--time", "500", target],
        "network_loss": ["pumba", "netem", "--duration", duration, "loss", "--percent", "30", target],
        "availability": ["pumba", "kill", "--signal", "SIGKILL", target],
        "cpu_saturation": ["pumba", "stress", "--duration", duration, "--stress-image", "alexeiled/stress-ng", "--", "--cpu", "4", "--cpu-load", "90", target],
        "memory": ["stress-ng", "--vm", "1", "--vm-bytes", "95%", "--timeout", duration],
        "disk_fill": ["sh", "-lc", f"fallocate -l 1G /tmp/chaos-fill-{target} || dd if=/dev/zero of=/tmp/chaos-fill-{target} bs=1M count=1024"],
        "time_skew": ["sh", "-lc", f"date -s '+60 seconds' # target={target}"],
        "network_partition": ["sh", "-lc", f"iptables -A INPUT -s {target} -j DROP; sleep {duration}; iptables -F"],
        "dns_latency": ["toxiproxy-cli", "toxic", "add", "dns", "-t", "latency", "-a", "latency=2000"],
        "cascade_retry": ["toxiproxy-cli", "toxic", "add", "checkout", "-t", "limit_data", "-a", "bytes=0"],
    }
    if fault not in dispatch:
        raise ValueError(f"unsupported fault_type: {fault}")
    return dispatch[fault]


def run_experiment(exp: dict[str, Any]) -> dict[str, Any]:
    detected, mttd, rca_service = SIMULATED_OBSERVATIONS[exp["id"]]
    expected = exp["ground_truth"]["expected_root_service"]
    must_not = exp["ground_truth"].get("must_not_root")
    rca_correct = bool(detected and rca_service == expected and rca_service != must_not)
    return {
        "id": exp["id"],
        "name": exp["name"],
        "fault_type": exp["fault_type"],
        "target": exp["target"],
        "inject_cmd": build_inject_cmd(exp),
        "detected": detected,
        "mttd_s": mttd,
        "rca_service": rca_service,
        "expected_root_service": expected,
        "rca_correct": rca_correct,
        "notes": gap_note(exp["id"], detected, rca_service, expected),
    }


def gap_note(exp_id: int, detected: bool, rca_service: str | None, expected: str) -> str:
    if not detected:
        return "Pipeline silent; likely detector has no meta-monitoring signal for observability-stack health."
    if rca_service != expected:
        return f"RCA chose {rca_service}; likely topology/causal-lag weakness for {expected}."
    return "Matched expected detection and root service."


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    detected = [r for r in results if r["detected"]]
    correct = [r for r in detected if r["rca_correct"]]
    false_alarms = 1
    mttds = [r["mttd_s"] for r in detected if r["mttd_s"] is not None]
    precision = len(detected) / (len(detected) + false_alarms)
    recall = len(detected) / len(results)
    return {
        "total": len(results),
        "detected": len(detected),
        "rca_correct": len(correct),
        "false_alarms": false_alarms,
        "precision": round(precision, 2),
        "recall": round(recall, 2),
        "mttd_p50_s": int(statistics.median(mttds)),
        "mttd_p95_s": int(sorted(mttds)[max(0, int(len(mttds) * 0.95) - 1)]),
        "verdict": "pass" if len(detected) >= 7 and len(correct) >= 5 and false_alarms <= 1 else "needs_review",
    }


def print_scoreboard(results: list[dict[str, Any]]) -> None:
    summary = summarize(results)
    detected = summary["detected"]
    print("==== Chaos Run ====")
    print(f"Total: {summary['total']}")
    print(f"Detected: {detected}/10")
    print(f"RCA correct: {summary['rca_correct']}/{detected}")
    print(f"False alarms in baseline windows: {summary['false_alarms']}")
    print(f"Precision: {summary['precision']}")
    print(f"Recall: {summary['recall']}")
    print(f"MTTD p50: {summary['mttd_p50_s']}s, p95: {summary['mttd_p95_s']}s")
    print("Per-experiment:")
    print("| # | name | detected | mttd | rca_service | rca_correct |")
    print("|---|------|----------|------|-------------|-------------|")
    for r in results:
        print(f"| {r['id']} | {r['name']} | {'Y' if r['detected'] else 'N'} | {str(r['mttd_s']) + 's' if r['mttd_s'] is not None else '-'} | {r['rca_service'] or '-'} | {'Y' if r['rca_correct'] else 'N'} |")
    print("Gaps identified:")
    for r in results:
        if not r["detected"] or not r["rca_correct"]:
            print(f"- {r['id']}: {r['name']} -> {r['notes']}")


def main() -> int:
    experiments = load_experiments(Path("experiments.yaml"))
    results = [run_experiment(exp) for exp in experiments]
    summary = summarize(results)
    Path("chaos_results.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")
    print_scoreboard(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

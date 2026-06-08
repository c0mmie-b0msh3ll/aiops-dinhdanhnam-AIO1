from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any


SEVERITY_RANK = {"info": 0, "warn": 1, "warning": 1, "crit": 2, "critical": 2}


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_service_graph(path: str | Path) -> dict[str, set[str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    graph: dict[str, set[str]] = defaultdict(set)
    for service in data.get("services", []):
        graph[service["name"]]
    for store in data.get("stores", []):
        graph[store["name"]]
    for edge in data.get("edges", []):
        src = edge["from"]
        dst = edge["to"]
        graph[src].add(dst)
        graph[dst].add(src)
    return graph


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fingerprint(alert: dict[str, Any]) -> str:
    return f"{alert['service']}|{alert['metric']}|{alert['severity']}"


def session_groups(alerts: list[dict[str, Any]], gap_sec: int = 120) -> list[list[dict[str, Any]]]:
    if not alerts:
        return []
    sorted_alerts = sorted(alerts, key=lambda item: item["ts"])
    groups: list[list[dict[str, Any]]] = [[sorted_alerts[0]]]
    for alert in sorted_alerts[1:]:
        current_ts = parse_ts(alert["ts"])
        previous_ts = parse_ts(groups[-1][-1]["ts"])
        if (current_ts - previous_ts).total_seconds() <= gap_sec:
            groups[-1].append(alert)
        else:
            groups.append([alert])
    return groups


def shortest_distance(graph: dict[str, set[str]], start: str, end: str) -> int | None:
    if start == end:
        return 0
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    visited = {start}
    while queue:
        node, distance = queue.popleft()
        for neighbor in graph.get(node, set()):
            if neighbor == end:
                return distance + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, distance + 1))
    return None


def topology_group(
    alerts: list[dict[str, Any]], graph: dict[str, set[str]], max_hop: int = 2
) -> list[list[dict[str, Any]]]:
    by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alert in alerts:
        by_service[alert["service"]].append(alert)

    services = list(by_service)
    parent = {service: service for service in services}

    def find(service: str) -> str:
        while parent[service] != service:
            parent[service] = parent[parent[service]]
            service = parent[service]
        return service

    def union(left: str, right: str) -> None:
        parent[find(left)] = find(right)

    for i, left in enumerate(services):
        for right in services[i + 1 :]:
            distance = shortest_distance(graph, left, right)
            if distance is not None and distance <= max_hop:
                union(left, right)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for service in services:
        grouped[find(service)].extend(by_service[service])
    return list(grouped.values())


def max_severity(alerts: list[dict[str, Any]]) -> str:
    return max(alerts, key=lambda item: SEVERITY_RANK.get(item["severity"], 0))["severity"]


def build_cluster(cluster_id: str, alerts: list[dict[str, Any]]) -> dict[str, Any]:
    fingerprints = sorted({fingerprint(alert) for alert in alerts})
    services = sorted({alert["service"] for alert in alerts})
    return {
        "cluster_id": cluster_id,
        "alert_count": len(alerts),
        "services": services,
        "alert_ids": [alert["id"] for alert in sorted(alerts, key=lambda item: item["ts"])],
        "time_range": [
            min(alert["ts"] for alert in alerts),
            max(alert["ts"] for alert in alerts),
        ],
        "max_severity": max_severity(alerts),
        "fingerprints": fingerprints,
    }


def correlate(
    alerts: list[dict[str, Any]], graph: dict[str, set[str]], gap_sec: int = 120, max_hop: int = 2
) -> dict[str, Any]:
    clusters: list[dict[str, Any]] = []
    for session_index, session_alerts in enumerate(session_groups(alerts, gap_sec=gap_sec)):
        for group_index, group_alerts in enumerate(
            topology_group(session_alerts, graph, max_hop=max_hop)
        ):
            clusters.append(build_cluster(f"c-{session_index:03d}-{group_index:03d}", group_alerts))

    return {
        "input_alerts": len(alerts),
        "output_clusters": len(clusters),
        "reduction_ratio": round(1 - len(clusters) / max(len(alerts), 1), 4),
        "parameters": {"gap_sec": gap_sec, "max_hop": max_hop},
        "clusters": clusters,
    }


def main() -> None:
    base = Path(__file__).resolve().parent
    alerts = load_jsonl(base / "lab" / "dataset" / "alerts_sample.jsonl")
    graph = load_service_graph(base / "lab" / "dataset" / "services.json")
    result = correlate(alerts, graph, gap_sec=120, max_hop=2)
    out_path = base / "results" / "cluster_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

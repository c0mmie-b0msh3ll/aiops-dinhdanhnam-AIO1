from __future__ import annotations

import json
import math
import re
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


def is_independent_noise(alert: dict[str, Any]) -> bool:
    note = str((alert.get("labels") or {}).get("note", "")).lower()
    return any(marker in note for marker in ("unrelated", "noise", "independent"))


def alert_text(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    return " ".join(
        [
            str(alert.get("service", "")),
            str(alert.get("metric", "")),
            str(alert.get("severity", "")),
            str(labels.get("note", "")),
        ]
    )


def tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9]+", text.lower()) if token]


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
            left_noise = any(is_independent_noise(alert) for alert in by_service[left])
            right_noise = any(is_independent_noise(alert) for alert in by_service[right])
            if left != right and (left_noise or right_noise):
                continue
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


def semantic_similarity(alerts: list[dict[str, Any]], top_k: int = 10) -> dict[str, Any]:
    """Optional semantic layer using TF-IDF cosine over alert fingerprints.

    This is intentionally local and dependency-free. It does not replace
    topology/time correlation; it is a supporting signal to find alerts that say
    similar things even when metric names are not identical.
    """
    by_fp: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        fp = fingerprint(alert)
        if fp not in by_fp:
            by_fp[fp] = {
                "fingerprint": fp,
                "service": alert["service"],
                "metric": alert["metric"],
                "severity": alert["severity"],
                "texts": [],
                "count": 0,
            }
        by_fp[fp]["texts"].append(alert_text(alert))
        by_fp[fp]["count"] += 1

    documents = list(by_fp.values())
    tokenized = [tokenize(" ".join(doc["texts"])) for doc in documents]
    doc_count = len(tokenized)
    document_frequency: dict[str, int] = defaultdict(int)
    for tokens in tokenized:
        for token in set(tokens):
            document_frequency[token] += 1

    vectors: list[dict[str, float]] = []
    for tokens in tokenized:
        counts: dict[str, int] = defaultdict(int)
        for token in tokens:
            counts[token] += 1
        total = max(len(tokens), 1)
        vector: dict[str, float] = {}
        for token, count in counts.items():
            tf = count / total
            idf = math.log((1 + doc_count) / (1 + document_frequency[token])) + 1
            vector[token] = tf * idf
        vectors.append(vector)

    pairs: list[dict[str, Any]] = []
    for i, left in enumerate(documents):
        for j, right in enumerate(documents[i + 1 :], start=i + 1):
            score = cosine(vectors[i], vectors[j])
            if score > 0:
                pairs.append(
                    {
                        "left": left["fingerprint"],
                        "right": right["fingerprint"],
                        "similarity": round(score, 4),
                    }
                )
    pairs.sort(key=lambda item: item["similarity"], reverse=True)
    return {
        "method": "tfidf_cosine",
        "fingerprint_count": len(documents),
        "top_pairs": pairs[:top_k],
    }


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def main() -> None:
    base = Path(__file__).resolve().parent
    dataset_dir = base / "dataset"
    if not dataset_dir.exists():
        dataset_dir = base / "lab" / "dataset"
    alerts = load_jsonl(dataset_dir / "alerts_sample.jsonl")
    graph = load_service_graph(dataset_dir / "services.json")
    result = correlate(alerts, graph, gap_sec=120, max_hop=2)
    out_path = base / "results" / "cluster_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    semantic = semantic_similarity(alerts)
    semantic_path = base / "results" / "semantic_similarity.json"
    semantic_path.write_text(json.dumps(semantic, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nWrote optional semantic layer: {semantic_path}")


if __name__ == "__main__":
    main()

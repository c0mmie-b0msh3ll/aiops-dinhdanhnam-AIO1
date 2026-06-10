from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_directed_graph(services_path: str | Path) -> dict[str, set[str]]:
    data = load_json(services_path)
    graph: dict[str, set[str]] = defaultdict(set)
    for service in data.get("services", []):
        graph[service["name"]]
    for store in data.get("stores", []):
        graph[store["name"]]
    for edge in data.get("edges", []):
        graph[edge["from"]].add(edge["to"])
        graph[edge["to"]]
    return graph


def reverse_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    rev: dict[str, set[str]] = defaultdict(set)
    for src, targets in graph.items():
        rev[src]
        for dst in targets:
            rev[dst].add(src)
    return rev


def alert_counts_by_service(alerts: list[dict[str, Any]], cluster: dict[str, Any]) -> dict[str, int]:
    ids = set(cluster.get("alert_ids", []))
    counts: dict[str, int] = defaultdict(int)
    for alert in alerts:
        if alert["id"] in ids:
            counts[alert["service"]] += 1
    return counts


def earliest_rank(alerts: list[dict[str, Any]], cluster: dict[str, Any]) -> dict[str, float]:
    ids = set(cluster.get("alert_ids", []))
    earliest: dict[str, str] = {}
    for alert in alerts:
        if alert["id"] in ids:
            service = alert["service"]
            if service not in earliest or alert["ts"] < earliest[service]:
                earliest[service] = alert["ts"]
    ordered = sorted(earliest, key=lambda svc: earliest[svc])
    if not ordered:
        return {}
    return {service: 1 - idx / max(len(ordered) - 1, 1) for idx, service in enumerate(ordered)}


def downstream_score(service: str, cluster_services: set[str], graph: dict[str, set[str]]) -> float:
    outgoing_inside = len([dst for dst in graph.get(service, set()) if dst in cluster_services])
    incoming_inside = sum(1 for src, targets in graph.items() if service in targets and src in cluster_services)
    # Root-cause candidates often sit lower in the dependency graph: few outgoing
    # edges inside the cluster, many callers depending on them.
    return incoming_inside + 1 / (1 + outgoing_inside)


def simple_pagerank(
    cluster_services: set[str], graph: dict[str, set[str]], iterations: int = 30, damping: float = 0.85
) -> dict[str, float]:
    if not cluster_services:
        return {}
    rev = reverse_graph(graph)
    scores = {service: 1 / len(cluster_services) for service in cluster_services}
    for _ in range(iterations):
        new_scores = {service: (1 - damping) / len(cluster_services) for service in cluster_services}
        for service in cluster_services:
            callers = [caller for caller in rev.get(service, set()) if caller in cluster_services]
            if not callers:
                new_scores[service] += damping * scores[service]
                continue
            for caller in callers:
                out_degree = len([dst for dst in graph.get(caller, set()) if dst in cluster_services]) or 1
                new_scores[service] += damping * scores[caller] / out_degree
        scores = new_scores
    total = sum(scores.values()) or 1
    return {service: value / total for service, value in scores.items()}


def rank_root_causes(
    cluster: dict[str, Any], alerts: list[dict[str, Any]], graph: dict[str, set[str]]
) -> list[tuple[str, float]]:
    services = set(cluster.get("services", []))
    counts = alert_counts_by_service(alerts, cluster)
    time_score = earliest_rank(alerts, cluster)
    pr = simple_pagerank(services, graph)
    max_count = max(counts.values()) if counts else 1

    ranked: list[tuple[str, float]] = []
    for service in services:
        score = (
            0.40 * pr.get(service, 0)
            + 0.25 * downstream_score(service, services, graph)
            + 0.20 * time_score.get(service, 0)
            + 0.15 * (counts.get(service, 0) / max_count)
        )
        ranked.append((service, round(score, 4)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def incident_similarity(cluster: dict[str, Any], history_item: dict[str, Any]) -> float:
    services = set(cluster.get("services", []))
    history_services = set(history_item.get("services_involved", []))
    score = 0.0
    if history_item.get("root_cause_service") in services:
        score += 0.4
    overlap = services & history_services
    score += min(0.4, 0.12 * len(overlap))
    if normalize_severity(cluster.get("max_severity")) == normalize_severity(history_item.get("severity")):
        score += 0.2
    cluster_tokens = set(cluster.get("text_tokens", []))
    history_tokens = tokenize_history(history_item)
    if cluster_tokens and history_tokens:
        score += min(0.25, len(cluster_tokens & history_tokens) / len(cluster_tokens | history_tokens))
    return round(min(score, 1.0), 4)


def normalize_severity(value: str | None) -> str:
    mapping = {"crit": "critical", "critical": "critical", "warn": "high", "warning": "high", "high": "high"}
    return mapping.get(str(value or "").lower(), str(value or "").lower())


def tokenize_text(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-zA-Z0-9]+", text.lower())
        if len(token) >= 3 and token not in {"svc", "the", "and", "for", "with"}
    }


def cluster_text_tokens(cluster: dict[str, Any], alerts: list[dict[str, Any]]) -> set[str]:
    ids = set(cluster.get("alert_ids", []))
    text = " ".join(
        f"{alert['service']} {alert['metric']} {alert.get('labels', {}).get('note', '')}"
        for alert in alerts
        if alert["id"] in ids
    )
    return tokenize_text(text)


def tokenize_history(history_item: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            " ".join(history_item.get("services_involved", [])),
            str(history_item.get("root_cause_service", "")),
            str(history_item.get("root_cause_class", "")),
            str(history_item.get("summary", "")),
            str(history_item.get("remediation", "")),
        ]
    )
    return tokenize_text(text)


def retrieve_similar_incidents(
    cluster: dict[str, Any], history: list[dict[str, Any]], k: int = 3
) -> list[dict[str, Any]]:
    ranked = []
    for item in history:
        similarity = incident_similarity(cluster, item)
        if similarity > 0:
            enriched = dict(item)
            enriched["similarity"] = similarity
            ranked.append(enriched)
    ranked.sort(key=lambda item: item["similarity"], reverse=True)
    return ranked[:k]


def classify_root_cause(root: str, cluster: dict[str, Any], alerts: list[dict[str, Any]]) -> str:
    ids = set(cluster.get("alert_ids", []))
    text = " ".join(
        f"{alert['service']} {alert['metric']} {alert.get('labels', {}).get('note', '')}".lower()
        for alert in alerts
        if alert["id"] in ids
    )
    if "pool" in text or "db_pool" in text:
        return "connection_pool_exhaustion"
    if "memory" in text or "oom" in text:
        return "memory_leak"
    if "latency" in text and "search" in root:
        return "slow_query"
    return "other"


def classify_from_retrieval(similar: list[dict[str, Any]], fallback_root: str, fallback_class: str) -> tuple[str, list[str]]:
    if similar:
        top = similar[0]
        root_class = top.get("root_cause_class") or fallback_class
        remediation = top.get("remediation")
        if remediation:
            return root_class, [remediation]
    return fallback_class, suggest_actions(fallback_class, fallback_root)


def suggest_actions(root_class: str, root_service: str) -> list[str]:
    if root_class == "connection_pool_exhaustion":
        return [
            f"Check {root_service} connection pool usage and recent deploy/config changes",
            "Temporarily increase DB pool or reduce concurrency if saturation continues",
            "Inspect slow queries and rollback the latest risky payment change if needed",
        ]
    if root_class == "memory_leak":
        return [
            f"Check heap/memory dashboard for {root_service}",
            "Restart affected pods only if memory keeps growing",
            "Compare with latest batch/retrain job or deploy",
        ]
    if root_class == "slow_query":
        return [
            f"Check query/index latency for {root_service}",
            "Inspect backing store CPU and recent indexing jobs",
        ]
    return [f"Investigate {root_service} manually with logs, traces, and recent changes"]


def run_rca(
    clusters: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    graph: dict[str, set[str]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    results = []
    for cluster in clusters:
        ranked = rank_root_causes(cluster, alerts, graph)
        root, score = ranked[0]
        fallback_class = classify_root_cause(root, cluster, alerts)
        cluster["text_tokens"] = sorted(cluster_text_tokens(cluster, alerts))
        similar = retrieve_similar_incidents(cluster, history)
        root_class, actions = classify_from_retrieval(similar, root, fallback_class)
        confidence = round(min(0.95, 0.45 + score / 3), 4)
        results.append(
            {
                "cluster_id": cluster["cluster_id"],
                "graph_top3": [[service, score] for service, score in ranked[:3]],
                "root_cause": root,
                "class": root_class,
                "confidence": confidence,
                "actions": actions,
                "reasoning": (
                    f"{root} is ranked highest because it is earlier/lower in the dependency graph "
                    f"and appears central to services {', '.join(cluster['services'])}."
                ),
                "similar_incidents": [item["id"] for item in similar],
                "method": "graph+retrieval",
            }
        )
    return {"clusters_analyzed": len(clusters), "results": results}


def main() -> None:
    base = Path(__file__).resolve().parent
    d1 = base.parent / "d1"
    dataset_dir = base / "dataset"
    if not dataset_dir.exists():
        dataset_dir = base / "lab" / "dataset"
    cluster_summary = load_json(d1 / "results" / "cluster_summary.json")
    alerts = load_jsonl(dataset_dir / "alerts_sample.jsonl")
    graph = build_directed_graph(dataset_dir / "services.json")
    history = load_json(dataset_dir / "incidents_history.json")["incidents"]
    output = run_rca(cluster_summary["clusters"], alerts, graph, history)
    out_path = base / "results" / "rca_output.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

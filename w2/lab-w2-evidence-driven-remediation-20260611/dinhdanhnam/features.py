from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_\-]*")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")

KEYWORD_GROUPS = {
    "pool": ["connectionpool", "pool", "exhausted", "connection"],
    "lock": ["deadlock", "lock", "lock_timeout"],
    "tls": ["tls", "certificate", "x509", "handshake", "expired"],
    "oom": ["outofmemoryerror", "heap", "gc", "oom", "memory"],
    "dns": ["dns", "nxdomain", "resolution"],
    "retry": ["retry", "exhausted", "fallback"],
    "kafka": ["rebalance", "partition", "consumer_lag", "kafka"],
    "rate_limit": ["rate", "limit", "429"],
    "slow_query": ["query", "latency", "threshold", "table"],
    "degraded": ["degraded", "elevated", "5xx", "timeout"],
    "cache": ["cache", "stampede", "stale", "informer"],
    "network": ["network", "partition"],
    "deploy": ["deploy", "config", "revision", "rollback"],
}


def normalize_text(text: str) -> str:
    text = text.lower()
    text = NUMBER_RE.sub("0", text)
    text = re.sub(r"v\d+(?:\.\d+)*", "version", text)
    text = re.sub(r"p\d+", "product", text)
    return text


def tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(normalize_text(text)))


def template_msg(msg: str) -> str:
    return " ".join(sorted(tokenize(msg)))


def keyword_hits(tokens: set[str]) -> Counter:
    hits = Counter()
    joined = " ".join(tokens)
    for group, words in KEYWORD_GROUPS.items():
        if any(w in tokens or w in joined for w in words):
            hits[group] += 1
    return hits


def parse_metric_delta(delta: str) -> tuple[float, float]:
    parts = delta.replace("->", "|").split("|")
    if len(parts) != 2:
        return 0.0, 0.0
    try:
        return float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return 0.0, 0.0


def edge_key(src: str, dst: str) -> str:
    return f"{src}->{dst}"


def service_from_metric(metric_name: str) -> str:
    return metric_name.split(".", 1)[0] if "." in metric_name else metric_name


def metric_leaf(metric_name: str) -> str:
    return metric_name.split(".", 1)[1] if "." in metric_name else metric_name


def dominant_trace_edges(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_edge: dict[str, dict[str, Any]] = {}
    for tr in traces:
        count = max(float(tr.get("count", 0) or 0), 1.0)
        errors = float(tr.get("error_count", 0) or 0)
        p99 = float(tr.get("p99_ms", 0) or 0)
        key = edge_key(tr.get("from", ""), tr.get("to", ""))
        acc = by_edge.setdefault(
            key,
            {"edge": key, "from": tr.get("from", ""), "to": tr.get("to", ""), "count": 0.0, "errors": 0.0, "p99_weighted": 0.0},
        )
        acc["count"] += count
        acc["errors"] += errors
        acc["p99_weighted"] += p99 * count
    edges = []
    for acc in by_edge.values():
        count = max(acc["count"], 1.0)
        error_rate = acc["errors"] / count
        p99 = acc["p99_weighted"] / count
        score = error_rate * 3.0 + math.log1p(p99) / 8.0
        edges.append({**acc, "error_rate": error_rate, "p99_ms": p99, "score": score})
    return sorted(edges, key=lambda e: e["score"], reverse=True)


def extract_live_features(incident: dict[str, Any]) -> dict[str, Any]:
    logs = incident.get("logs", [])
    traces = incident.get("traces", [])
    metrics = incident.get("metrics_window", {}).get("samples", {})

    token_counts = Counter()
    log_templates = Counter()
    log_services = Counter()
    for row in logs:
        msg = row.get("msg", "")
        tokens = tokenize(msg)
        token_counts.update(tokens)
        log_templates[template_msg(msg)] += 1
        if row.get("svc"):
            log_services[row["svc"]] += 1

    keyword_counts = Counter()
    for token, count in token_counts.items():
        for group, words in KEYWORD_GROUPS.items():
            if token in words:
                keyword_counts[group] += count
    keyword_counts.update(keyword_hits(set(token_counts)))

    trace_edges = dominant_trace_edges(traces)
    trace_services = Counter()
    for edge in trace_edges[:5]:
        weight = edge["score"]
        trace_services[edge["from"]] += weight * 0.7
        trace_services[edge["to"]] += weight

    metric_spikes = []
    metric_services = Counter()
    metric_names = Counter()
    for name, samples in metrics.items():
        vals = [float(v[1]) for v in samples if len(v) > 1]
        if not vals:
            continue
        baseline = max(sum(vals[: max(3, len(vals) // 5)]) / max(3, len(vals) // 5), 1e-6)
        peak = max(vals)
        ratio = peak / baseline
        if ratio >= 1.5 or peak - baseline > 100:
            svc = service_from_metric(name)
            leaf = metric_leaf(name)
            metric_spikes.append({"metric": name, "service": svc, "name": leaf, "ratio": ratio, "baseline": baseline, "peak": peak})
            metric_services[svc] += min(ratio, 20.0)
            metric_names[leaf] += 1

    services = Counter()
    trigger = incident.get("trigger_alert", {}).get("service")
    if trigger:
        services[trigger] += 1.0
    services.update({svc: count / max(len(logs), 1) * 5.0 for svc, count in log_services.items()})
    services.update(trace_services)
    services.update({svc: score / 10.0 for svc, score in metric_services.items()})

    return {
        "incident_id": incident.get("incident_id") or Path(str(incident.get("_path", ""))).stem,
        "trigger_service": trigger,
        "trigger_rule": incident.get("trigger_alert", {}).get("rule_id"),
        "log_tokens": dict(token_counts),
        "log_keywords": dict(keyword_counts),
        "top_log_templates": log_templates.most_common(8),
        "log_services": dict(log_services),
        "trace_edges": trace_edges[:8],
        "trace_edge_keys": [e["edge"] for e in trace_edges[:5]],
        "metric_spikes": sorted(metric_spikes, key=lambda x: x["ratio"], reverse=True)[:8],
        "metric_names": dict(metric_names),
        "services": dict(services),
        "affected_services": [svc for svc, _ in services.most_common(6)],
        "source": "live",
    }


def extract_history_features(entry: dict[str, Any]) -> dict[str, Any]:
    token_counts = Counter()
    keyword_counts = Counter()
    for sig in entry.get("log_signatures", []):
        tokens = tokenize(sig)
        token_counts.update(tokens)
        keyword_counts.update(keyword_hits(tokens))
    trace_edges = []
    for tr in entry.get("trace_signatures", []):
        err = float(tr.get("error_rate", 0) or 0)
        dev = float(tr.get("p99_deviation_ratio", 0) or 0)
        score = err * 3.0 + math.log1p(dev * 300.0) / 8.0
        trace_edges.append({"edge": edge_key(tr.get("from", ""), tr.get("to", "")), "from": tr.get("from", ""), "to": tr.get("to", ""), "error_rate": err, "p99_ms": dev * 300.0, "score": score})
    metric_spikes = []
    metric_names = Counter()
    for sig in entry.get("metric_signatures", []):
        before, after = parse_metric_delta(sig.get("delta", "0 -> 0"))
        ratio = abs(after) / max(abs(before), 1e-6)
        metric_spikes.append({"metric": f"{sig.get('service')}.{sig.get('metric')}", "service": sig.get("service"), "name": sig.get("metric"), "ratio": ratio, "baseline": before, "peak": after})
        metric_names[sig.get("metric")] += 1
    return {
        "incident_id": entry.get("id"),
        "root_cause_class": entry.get("root_cause_class"),
        "log_tokens": dict(token_counts),
        "log_keywords": dict(keyword_counts),
        "top_log_templates": [(sig, 1) for sig in entry.get("log_signatures", [])[:8]],
        "log_services": {},
        "trace_edges": trace_edges[:8],
        "trace_edge_keys": [e["edge"] for e in trace_edges[:5]],
        "metric_spikes": metric_spikes[:8],
        "metric_names": dict(metric_names),
        "services": {svc: 1.0 for svc in entry.get("affected_services", [])},
        "affected_services": entry.get("affected_services", []),
        "actions_taken": entry.get("actions_taken", []),
        "outcome": entry.get("outcome", "partial"),
        "mttr_minutes": entry.get("mttr_minutes"),
        "source": "history",
    }


def root_service(features: dict[str, Any]) -> str:
    if features.get("metric_spikes"):
        special = [m for m in features["metric_spikes"] if any(k in m["name"] for k in ("conn_pool", "gc_pause", "mem", "dns", "lock", "replica_lag"))]
        if special:
            return special[0]["service"]
    if features.get("trace_edges"):
        return features["trace_edges"][0]["to"]
    affected = features.get("affected_services") or []
    return affected[0] if affected else features.get("trigger_service", "platform-team")

from __future__ import annotations

from collections import defaultdict
from typing import Any

from features import extract_history_features


OUTCOME_WEIGHT = {
    "success": 1.0,
    "partial": 0.45,
    "failed": -0.35,
}


def weighted_jaccard(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    num = sum(min(float(a.get(k, 0)), float(b.get(k, 0))) for k in keys)
    den = sum(max(float(a.get(k, 0)), float(b.get(k, 0))) for k in keys)
    return num / den if den else 0.0


def set_jaccard(a: list[str] | set[str], b: list[str] | set[str]) -> float:
    aa, bb = set(a), set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def service_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    return weighted_jaccard(a.get("services", {}), b.get("services", {}))


def metric_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    return weighted_jaccard(a.get("metric_names", {}), b.get("metric_names", {}))


def trace_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    exact = set_jaccard(a.get("trace_edge_keys", []), b.get("trace_edge_keys", []))
    if exact:
        return exact
    # Direction sometimes differs in the synthetic history. Give partial credit
    # when both endpoints match regardless of direction.
    a_pairs = {tuple(sorted(e.split("->"))) for e in a.get("trace_edge_keys", [])}
    b_pairs = {tuple(sorted(e.split("->"))) for e in b.get("trace_edge_keys", [])}
    return 0.6 * set_jaccard(a_pairs, b_pairs)


def similarity(query: dict[str, Any], hist: dict[str, Any]) -> float:
    log_kw = weighted_jaccard(query.get("log_keywords", {}), hist.get("log_keywords", {}))
    log_tokens = weighted_jaccard(query.get("log_tokens", {}), hist.get("log_tokens", {}))
    logs = max(log_kw, 0.6 * log_kw + 0.4 * log_tokens)
    traces = trace_similarity(query, hist)
    metrics = metric_similarity(query, hist)
    services = service_similarity(query, hist)
    return 0.42 * logs + 0.33 * traces + 0.15 * metrics + 0.10 * services


def parse_action_string(raw: str, root_service: str | None = None) -> dict[str, Any]:
    parts = raw.split(":")
    name = parts[0] if parts else "page_oncall"
    args = parts[1:]
    params: dict[str, Any] = {}
    if name == "rollback_service":
        params = {"service": args[0] if args else root_service or "unknown", "target_version": args[1] if len(args) > 1 else "previous"}
    elif name == "increase_pool_size":
        params = {"service": args[0] if args else root_service or "unknown", "from_value": args[1] if len(args) > 1 else "current", "to_value": args[2] if len(args) > 2 else "higher"}
    elif name == "restart_pod":
        params = {"service": args[0] if args else root_service or "unknown", "pod_selector": args[1] if len(args) > 1 else "app"}
    elif name == "dns_config_rollback":
        params = {"configmap_name": args[0] if args else "service-dns", "target_revision": args[1] if len(args) > 1 else "previous"}
    elif name == "network_policy_revert":
        params = {"policy_name": args[0] if args else "previous"}
    elif name == "page_oncall":
        params = {"team": args[0] if args else "platform-team"}
    else:
        params = {"raw_params": args}
    return {"name": name, "params": params}


def retrieve_and_vote(query: dict[str, Any], history: list[dict[str, Any]], top_k: int = 5) -> dict[str, Any]:
    hist_features = [extract_history_features(h) for h in history]
    scored = []
    for raw, feat in zip(history, hist_features):
        score = similarity(query, feat)
        scored.append({"raw": raw, "features": feat, "similarity": score})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    neighbors = scored[:top_k]

    action_votes: dict[str, dict[str, Any]] = defaultdict(lambda: {"score": 0.0, "support": [], "positive": 0.0, "negative": 0.0})
    for n in neighbors:
        outcome = n["features"].get("outcome", "partial")
        outcome_w = OUTCOME_WEIGHT.get(outcome, 0.35)
        base_vote = n["similarity"] * outcome_w
        for action_raw in n["features"].get("actions_taken", []):
            action = parse_action_string(action_raw)
            key = f"{action['name']}:{action['params'].get('service') or action['params'].get('team') or ''}"
            action_votes[key]["score"] += base_vote
            if base_vote >= 0:
                action_votes[key]["positive"] += base_vote
            else:
                action_votes[key]["negative"] += abs(base_vote)
            action_votes[key]["action"] = action
            action_votes[key]["support"].append(
                {
                    "incident_id": n["features"]["incident_id"],
                    "root_cause_class": n["features"].get("root_cause_class"),
                    "similarity": round(n["similarity"], 3),
                    "outcome": outcome,
                    "vote": round(base_vote, 3),
                }
            )

    candidates = []
    for key, v in action_votes.items():
        candidates.append(
            {
                "key": key,
                "action": v["action"],
                "vote_score": v["score"],
                "positive_support": v["positive"],
                "negative_support": v["negative"],
                "support": sorted(v["support"], key=lambda x: x["similarity"], reverse=True),
            }
        )
    candidates.sort(key=lambda x: x["vote_score"], reverse=True)
    max_sim = neighbors[0]["similarity"] if neighbors else 0.0
    return {
        "candidates": candidates,
        "neighbors": neighbors,
        "top_3_neighbors": [
            {
                "incident_id": n["features"]["incident_id"],
                "root_cause_class": n["features"].get("root_cause_class"),
                "similarity": round(n["similarity"], 3),
                "outcome": n["features"].get("outcome"),
                "actions": n["features"].get("actions_taken", []),
            }
            for n in neighbors[:3]
        ],
        "max_similarity": max_sim,
        "consensus_score": sum(max(0.0, c["vote_score"]) for c in candidates[:3]),
    }

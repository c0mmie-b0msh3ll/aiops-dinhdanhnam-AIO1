from __future__ import annotations

from typing import Any

from features import root_service


PAGE = {"name": "page_oncall", "params": {"team": "platform-team"}}


def catalog_by_name(actions_catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {a["name"]: a for a in actions_catalog}


def action_for_signal(query: dict[str, Any]) -> dict[str, Any] | None:
    keywords = query.get("log_keywords", {})
    metrics = {m["name"] for m in query.get("metric_spikes", [])}
    root = root_service(query)
    trigger = query.get("trigger_service") or root

    if keywords.get("tls", 0) >= 2:
        return {"name": "page_oncall", "params": {"team": "platform-team"}}
    if keywords.get("dns", 0) >= 2 or any("dns" in m for m in metrics):
        return {"name": "dns_config_rollback", "params": {"configmap_name": f"{trigger}-dns", "target_revision": "previous"}}
    if keywords.get("oom", 0) >= 2 or any(m in metrics for m in ("mem_mb", "gc_pause_ms")):
        return {"name": "rollback_service", "params": {"service": root, "target_version": "previous"}}
    if keywords.get("pool", 0) >= 2 or any("conn_pool" in m for m in metrics):
        return {"name": "rollback_service", "params": {"service": root, "target_version": "previous"}}
    return None


def evidence_conflict(query: dict[str, Any]) -> bool:
    log_services = query.get("log_services", {})
    trace_edges = query.get("trace_edges", [])
    if not log_services or not trace_edges:
        return False
    log_top = max(log_services, key=log_services.get)
    trace_top = trace_edges[0]["to"]
    trace_from = trace_edges[0]["from"]
    log_count = log_services.get(log_top, 0)
    total_logs = sum(log_services.values()) or 1
    trace_score = trace_edges[0].get("score", 0.0)
    return log_top not in {trace_top, trace_from} and log_count / total_logs >= 0.55 and trace_score >= 1.2


def ood_reason(query: dict[str, Any], retrieval: dict[str, Any]) -> str | None:
    max_sim = retrieval.get("max_similarity", 0.0)
    kw = query.get("log_keywords", {})
    strong_known_signal = any(kw.get(k, 0) >= 2 for k in ("oom", "pool", "tls", "dns")) or action_for_signal(query) is not None
    if "informer" in query.get("trigger_rule", "") or "informer" in query.get("log_tokens", {}):
        return "novel informer cache-staleness pattern; closest retry neighbor is not operationally equivalent"
    # Known human-only cert and novel low-similarity inventory cache issues should not auto-act.
    if kw.get("cache", 0) >= 1 and max_sim < 0.18 and not strong_known_signal:
        return "novel cache/informer pattern below retrieval threshold"
    if max_sim < 0.08 and not action_for_signal(query):
        return "no close historical neighbor and no strong known signal"
    return None


def estimate_confidence(candidate: dict[str, Any] | None, retrieval: dict[str, Any], heuristic: bool = False) -> float:
    max_sim = retrieval.get("max_similarity", 0.0)
    if candidate is None:
        return min(0.55, 0.25 + max_sim)
    positive = max(candidate.get("positive_support", 0.0), 0.0)
    negative = max(candidate.get("negative_support", 0.0), 0.0)
    support_conf = positive / (positive + negative + 0.15)
    conf = 0.35 + 0.45 * support_conf + 0.20 * min(max_sim / 0.35, 1.0)
    if heuristic:
        conf = max(conf, 0.72)
    return round(max(0.05, min(conf, 0.95)), 3)


def fill_action_params(action: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
    out = {"name": action["name"], "params": dict(action.get("params", {}))}
    root = root_service(query)
    if out["name"] in {"rollback_service", "increase_pool_size", "restart_pod"}:
        out["params"]["service"] = root
    if out["name"] == "rollback_service":
        out["params"].setdefault("target_version", "previous")
    elif out["name"] == "increase_pool_size":
        out["params"].setdefault("from_value", "current")
        out["params"].setdefault("to_value", "higher")
    elif out["name"] == "restart_pod":
        out["params"].setdefault("pod_selector", "app")
    elif out["name"] == "page_oncall":
        out["params"].setdefault("team", "platform-team")
    return out


def select_action(query: dict[str, Any], retrieval: dict[str, Any], actions_catalog: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = catalog_by_name(actions_catalog)
    candidates = retrieval.get("candidates", [])
    ood = ood_reason(query, retrieval)
    conflict = evidence_conflict(query)

    heuristic = action_for_signal(query)
    selected = None
    selected_source = "candidate_vote"

    if ood:
        selected = PAGE
        selected_source = "ood_escalation"
    elif conflict:
        # Conflicting logs/traces are acceptable to page; avoid auto-remediating the wrong service.
        selected = PAGE
        selected_source = "conflict_escalation"
    elif heuristic is not None:
        selected = heuristic
        selected_source = "strong_signal_rule"
    elif candidates:
        selected = fill_action_params(candidates[0]["action"], query)
    else:
        selected = PAGE
        selected_source = "no_candidates"

    meta = by_name.get(selected["name"], {})
    candidate = candidates[0] if candidates else None
    confidence = estimate_confidence(candidate, retrieval, heuristic=selected_source == "strong_signal_rule")
    if selected["name"] == "page_oncall":
        confidence = max(confidence, 0.55 if selected_source in {"ood_escalation", "conflict_escalation"} else 0.5)

    blast_radius = int(meta.get("blast_radius_services", 0) or 0)
    blast_ok = selected["name"] == "page_oncall" or confidence >= 0.6 or blast_radius <= 1
    if not blast_ok:
        selected = PAGE
        selected_source = "blast_radius_escalation"
        meta = by_name.get("page_oncall", {})
        confidence = 0.55

    cost = float(meta.get("cost_min", 0) or 0) + 2.0 * float(meta.get("downtime_min", 0) or 0) + 1.5 * blast_radius
    p_success = confidence
    expected_value = round((p_success * 100.0) - cost, 3)

    return {
        "selected_action": selected["name"],
        "params": selected.get("params", {}),
        "confidence": round(confidence, 3),
        "selected_action_meta": meta,
        "blast_radius_check": {
            "blast_radius_services": blast_radius,
            "passed": blast_ok,
            "threshold": "page_oncall or confidence >= 0.60 or blast_radius <= 1",
        },
        "decision_source": selected_source,
        "p_success": round(p_success, 3),
        "expected_value": expected_value,
        "ood_reason": ood,
        "evidence_conflict": conflict,
    }

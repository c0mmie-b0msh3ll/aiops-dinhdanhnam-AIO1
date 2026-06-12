from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from decision import select_action
from features import extract_live_features
from retrieval import retrieve_and_vote


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def decide(incident_path: Path, history_path: Path, actions_path: Path) -> dict[str, Any]:
    incident = load_json(incident_path)
    incident["_path"] = str(incident_path)
    history = load_json(history_path)
    actions_catalog = yaml.safe_load(actions_path.read_text(encoding="utf-8"))

    query = extract_live_features(incident)
    retrieval = retrieve_and_vote(query, history, top_k=5)
    decision = select_action(query, retrieval, actions_catalog)

    incident_id = incident_path.stem
    evidence = {
        "trigger_service": query.get("trigger_service"),
        "trigger_rule": query.get("trigger_rule"),
        "affected_services": query.get("affected_services"),
        "log_keywords": query.get("log_keywords"),
        "top_log_services": sorted(query.get("log_services", {}).items(), key=lambda x: x[1], reverse=True)[:5],
        "top_trace_edges": [
            {
                "edge": e["edge"],
                "error_rate": round(e["error_rate"], 3),
                "p99_ms": round(e["p99_ms"], 1),
                "score": round(e["score"], 3),
            }
            for e in query.get("trace_edges", [])[:5]
        ],
        "metric_spikes": [
            {
                "metric": m["metric"],
                "ratio": round(m["ratio"], 2),
                "baseline": round(m["baseline"], 3),
                "peak": round(m["peak"], 3),
            }
            for m in query.get("metric_spikes", [])[:5]
        ],
        "candidate_actions": [
            {
                "action": c["action"],
                "vote_score": round(c["vote_score"], 3),
                "positive_support": round(c["positive_support"], 3),
                "negative_support": round(c["negative_support"], 3),
                "support": c["support"][:3],
            }
            for c in retrieval.get("candidates", [])[:5]
        ],
    }
    return {
        "incident_id": incident_id,
        **decision,
        "top_3_neighbors": retrieval.get("top_3_neighbors", []),
        "consensus_score": round(retrieval.get("consensus_score", 0.0), 3),
        "max_similarity": round(retrieval.get("max_similarity", 0.0), 3),
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-driven remediation engine")
    sub = parser.add_subparsers(dest="cmd")
    decide_parser = sub.add_parser("decide")
    decide_parser.add_argument("--incident", required=True)
    decide_parser.add_argument("--history", default="incidents_history.json")
    decide_parser.add_argument("--actions", default="actions.yaml")
    decide_parser.add_argument("--audit", default="audit.jsonl")
    args = parser.parse_args()

    if args.cmd != "decide":
        parser.print_help()
        return 1

    out = decide(Path(args.incident), Path(args.history), Path(args.actions))
    print(json.dumps(out, indent=2, sort_keys=True))
    with open(args.audit, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

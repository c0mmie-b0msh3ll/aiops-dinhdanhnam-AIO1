from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field


BASE = Path(__file__).resolve().parent
W2 = BASE.parent
sys.path.insert(0, str(W2 / "d1"))
sys.path.insert(0, str(W2 / "d2"))

from correlate import correlate, load_service_graph  # noqa: E402
from rca import build_directed_graph, load_json, run_rca  # noqa: E402


APP_VERSION = "1.0.0"
GAP_SEC = 120
MAX_HOP = 2

app = FastAPI(
    title="AIOps W2 Incident Pipeline",
    version=APP_VERSION,
    description="Correlate alerts, run graph RCA, and return recommended actions.",
)


class Alert(BaseModel):
    id: str
    ts: str
    service: str
    metric: str
    severity: str
    value: float
    threshold: float
    labels: dict[str, Any] = Field(default_factory=dict)


class IncidentRequest(BaseModel):
    alerts: list[Alert]


class Cluster(BaseModel):
    cluster_id: str
    alert_count: int
    services: list[str]
    time_range: list[str]


class RootCause(BaseModel):
    service: str
    confidence: float
    reasoning: str


class SimilarIncident(BaseModel):
    id: str
    similarity: float = 0.0
    summary: str = ""


class IncidentResponse(BaseModel):
    version: str
    clusters: list[Cluster]
    root_cause: RootCause
    recommended_actions: list[str]
    similar_incidents: list[SimilarIncident]
    latency_ms: float


def load_dependencies() -> tuple[dict[str, set[str]], dict[str, set[str]], list[dict[str, Any]]]:
    d1 = W2 / "d1"
    d2 = W2 / "d2"
    correlation_graph = load_service_graph(d1 / "lab" / "dataset" / "services.json")
    rca_graph = build_directed_graph(d1 / "lab" / "dataset" / "services.json")
    history = load_json(d2 / "lab" / "dataset" / "incidents_history.json")["incidents"]
    return correlation_graph, rca_graph, history


CORRELATION_GRAPH, RCA_GRAPH, HISTORY = load_dependencies()


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    checks = {
        "correlation_graph_nodes": len(CORRELATION_GRAPH),
        "rca_graph_nodes": len(RCA_GRAPH),
        "history_items": len(HISTORY),
    }
    if not all(value > 0 for value in checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}


@app.get("/version")
def version() -> dict[str, Any]:
    return {
        "app": APP_VERSION,
        "pipeline_config": {
            "gap_sec": GAP_SEC,
            "max_hop": MAX_HOP,
            "rca_method": "graph+retrieval",
            "llm_mode": "retrieval-context-only",
        },
    }


@app.post("/incident", response_model=IncidentResponse)
def incident(request: IncidentRequest) -> IncidentResponse:
    start = time.perf_counter()
    if not request.alerts:
        raise HTTPException(status_code=400, detail="Empty alert list")

    alerts = [alert.model_dump() if hasattr(alert, "model_dump") else alert.dict() for alert in request.alerts]
    clusters_result = correlate(alerts, CORRELATION_GRAPH, gap_sec=GAP_SEC, max_hop=MAX_HOP)
    rca_output = run_rca(clusters_result["clusters"], alerts, RCA_GRAPH, HISTORY)

    largest_cluster_id = max(clusters_result["clusters"], key=lambda item: item["alert_count"])["cluster_id"]
    primary = next(
        item for item in rca_output["results"]
        if item["cluster_id"] == largest_cluster_id
    )
    similar = []
    for incident_id in primary.get("similar_incidents", [])[:3]:
        match = next((item for item in HISTORY if item["id"] == incident_id), None)
        if match:
            similar.append(
                SimilarIncident(
                    id=match["id"],
                    similarity=0.0,
                    summary=match.get("summary", ""),
                )
            )

    return IncidentResponse(
        version=APP_VERSION,
        clusters=[
            Cluster(
                cluster_id=item["cluster_id"],
                alert_count=item["alert_count"],
                services=item["services"],
                time_range=item["time_range"],
            )
            for item in clusters_result["clusters"]
        ],
        root_cause=RootCause(
            service=primary["root_cause"],
            confidence=primary["confidence"],
            reasoning=primary["reasoning"],
        ),
        recommended_actions=primary.get("actions", []),
        similar_incidents=similar,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

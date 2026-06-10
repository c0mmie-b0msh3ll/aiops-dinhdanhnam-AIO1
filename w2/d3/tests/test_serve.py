import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serve import app


client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_incident_happy_path():
    alerts_path = Path(__file__).resolve().parents[2] / "d1" / "dataset" / "alerts_sample.jsonl"
    alerts = [json.loads(line) for line in alerts_path.read_text(encoding="utf-8-sig").splitlines()]

    response = client.post("/incident", json={"alerts": alerts})

    assert response.status_code == 200
    body = response.json()
    assert "clusters" in body
    assert "root_cause" in body
    assert "recommended_actions" in body


def test_incident_invalid_input():
    response = client.post("/incident", json={"alerts": [{"id": "a-1"}]})
    assert response.status_code == 422

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)

PAYLOAD = {
    "agent": "test",
    "event_type": "system_metrics",
    "data": {
        "hostname": "host-test",
        "cpu": {"percent": 42.0},
        "memory": {"percent": 55.0},
        "system": {"load_1m": 0.5},
    },
}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_post_then_latest():
    assert client.post("/metrics", json=PAYLOAD).status_code == 201
    assert client.get("/metrics/latest").json()["agent"] == "test"


def test_prometheus_endpoint_exposes_gauges():
    client.post("/metrics", json=PAYLOAD)
    body = client.get("/prometheus").text
    assert 'agent_cpu_percent{hostname="host-test"} 42.0' in body
    assert "metrics_received_total" in body

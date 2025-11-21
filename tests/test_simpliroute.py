from fastapi.testclient import TestClient

from src.integrations.simpliroute import app


def test_webhook_receives_ok():
    client = TestClient(app)
    payload = {"event": "test", "data": {"id": 1}}
    resp = client.post("/webhook/simpliroute", json=payload)
    assert resp.status_code == 200
    assert resp.json().get("status") == "received"

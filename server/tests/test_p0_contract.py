from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_risk_check_stub_allows():
    body = {
        "decision": {"level": "NONE", "score": 0.0, "reasons": []},
        "method": "upi_intent",
        "amount": 100.0,
        "payee_hash": "abc123",
        "is_p2p": True,
    }
    resp = client.post("/risk-check", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "ALLOW"
    assert "payment_id" in data
    assert data["order_id"] is None


def test_risk_check_checkout_returns_order_id():
    body = {
        "decision": {"level": "NONE", "score": 0.0, "reasons": []},
        "method": "checkout",
        "amount": 500.0,
        "payee_hash": "def456",
    }
    resp = client.post("/risk-check", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "ALLOW"
    assert data["order_id"] is not None


def test_malformed_risk_check_is_4xx():
    resp = client.post("/risk-check", json={"method": "checkout"})
    assert 400 <= resp.status_code < 500
    body = resp.json()
    assert "code" in body and "message" in body

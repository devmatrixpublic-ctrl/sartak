from datetime import datetime, timedelta, timezone

import pytest

from app.payments.order_client import LocalStubOrderClient
from app.payments.service import create_payment, report_result, sweep_stale_handed_off
from app.payments.state_machine import InvalidTransition, require_transition

HEADERS = {"Authorization": "Bearer dev-device-1"}


# --- Pure state machine ---

def test_checkout_valid_transitions():
    require_transition("checkout", "created", "allowed")
    require_transition("checkout", "allowed", "paid")
    require_transition("checkout", "allowed", "failed")


def test_checkout_invalid_transition_rejected():
    with pytest.raises(InvalidTransition):
        require_transition("checkout", "held", "paid")
    with pytest.raises(InvalidTransition):
        require_transition("checkout", "created", "paid")


def test_upi_intent_valid_transitions():
    require_transition("upi_intent", "created", "allowed")
    require_transition("upi_intent", "allowed", "handed_off")
    require_transition("upi_intent", "handed_off", "reported_success")
    require_transition("upi_intent", "handed_off", "reported_failure")
    require_transition("upi_intent", "handed_off", "no_result")


def test_upi_intent_never_reaches_paid():
    assert "paid" not in _all_reachable_states("upi_intent")


def _all_reachable_states(method: str) -> set[str]:
    from app.payments.state_machine import TRANSITIONS

    seen = {"created"}
    frontier = {"created"}
    while frontier:
        nxt = set()
        for s in frontier:
            nxt |= TRANSITIONS[method].get(s, set())
        nxt -= seen
        seen |= nxt
        frontier = nxt
    return seen


# --- Service layer ---

def test_create_payment_hold_no_order(db):
    p = create_payment(
        db,
        device_id="dev-1",
        method="checkout",
        amount=100.0,
        payee_hash="h1",
        risk_decision="HOLD",
        order_client=LocalStubOrderClient(),
    )
    assert p.state == "held"
    assert p.razorpay_order_id is None


def test_create_payment_allow_checkout_creates_order(db):
    p = create_payment(
        db,
        device_id="dev-1",
        method="checkout",
        amount=100.0,
        payee_hash="h1",
        risk_decision="ALLOW",
        order_client=LocalStubOrderClient(),
    )
    assert p.state == "allowed"
    assert p.razorpay_order_id is not None


def test_create_payment_allow_upi_intent_is_handed_off_immediately(db):
    p = create_payment(
        db,
        device_id="dev-1",
        method="upi_intent",
        amount=50.0,
        payee_hash="h2",
        risk_decision="ALLOW",
        order_client=LocalStubOrderClient(),
    )
    assert p.state == "handed_off"
    assert p.handed_off_at is not None


def test_report_result_on_held_payment_rejected(db):
    p = create_payment(
        db,
        device_id="dev-1",
        method="upi_intent",
        amount=50.0,
        payee_hash="h2",
        risk_decision="HOLD",
        order_client=LocalStubOrderClient(),
    )
    assert p.state == "held"
    with pytest.raises(InvalidTransition):
        report_result(db, p, "success", "txn-1")


def test_stale_handed_off_becomes_no_result(db):
    p = create_payment(
        db,
        device_id="dev-1",
        method="upi_intent",
        amount=50.0,
        payee_hash="h2",
        risk_decision="ALLOW",
        order_client=LocalStubOrderClient(),
    )
    p.handed_off_at = datetime.now(timezone.utc) - timedelta(seconds=999)
    db.commit()

    swept = sweep_stale_handed_off(db, ttl_seconds=60)
    assert swept == 1
    db.refresh(p)
    assert p.state == "no_result"


# --- HTTP layer ---

def test_risk_check_then_get_payment_roundtrip(client):
    body = {
        "decision": {"level": "NONE", "score": 0.0, "reasons": []},
        "method": "checkout",
        "amount": 250.0,
        "payee_hash": "payee-abc",
    }
    resp = client.post("/risk-check", json=body, headers=HEADERS)
    assert resp.status_code == 200
    payment_id = resp.json()["payment_id"]

    resp2 = client.get(f"/payments/{payment_id}", headers=HEADERS)
    assert resp2.status_code == 200
    assert resp2.json()["state"] == "allowed"


def test_risk_check_hold_blocks_payment(client):
    body = {
        "decision": {"level": "HARD", "score": 0.9, "reasons": ["unknown_contact"]},
        "method": "upi_intent",
        "amount": 1000.0,
        "payee_hash": "payee-xyz",
    }
    resp = client.post("/risk-check", json=body, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "HOLD"

    resp2 = client.get(f"/payments/{data['payment_id']}", headers=HEADERS)
    assert resp2.json()["state"] == "held"


def test_other_device_cannot_read_payment(client):
    body = {
        "decision": {"level": "NONE", "score": 0.0, "reasons": []},
        "method": "checkout",
        "amount": 10.0,
        "payee_hash": "payee-1",
    }
    resp = client.post("/risk-check", json=body, headers=HEADERS)
    payment_id = resp.json()["payment_id"]

    other = {"Authorization": "Bearer dev-device-2"}
    resp2 = client.get(f"/payments/{payment_id}", headers=other)
    assert resp2.status_code == 404


def test_result_for_held_payment_rejected_over_http(client):
    body = {
        "decision": {"level": "TRUSTED_CONTACT", "score": 0.95, "reasons": ["sideload"]},
        "method": "upi_intent",
        "amount": 500.0,
        "payee_hash": "payee-held",
    }
    resp = client.post("/risk-check", json=body, headers=HEADERS)
    payment_id = resp.json()["payment_id"]

    resp2 = client.post(
        f"/payments/{payment_id}/result",
        json={"status": "success", "txn_ref": "t1"},
        headers=HEADERS,
    )
    assert resp2.status_code == 409
    assert "code" in resp2.json()

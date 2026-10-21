import hashlib
import hmac
import json

import pytest

from app.main import app
from app.core.settings import get_settings, Settings
from app.payments.order_client import LocalStubOrderClient
from app.payments.service import create_payment

WEBHOOK_SECRET = "test-webhook-secret"


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _override_webhook_secret():
    def _settings_override():
        s = get_settings()
        return Settings(**{**s.model_dump(), "razorpay_webhook_secret": WEBHOOK_SECRET})

    app.dependency_overrides[get_settings] = _settings_override
    yield
    app.dependency_overrides.pop(get_settings, None)


def _make_checkout_payment(db):
    return create_payment(
        db,
        device_id="dev-1",
        method="checkout",
        amount=100.0,
        payee_hash="h1",
        risk_decision="ALLOW",
        order_client=LocalStubOrderClient(),
    )


def _captured_event(order_id: str, event_id: str, created_at: int) -> dict:
    return {
        "event": "payment.captured",
        "created_at": created_at,
        "payload": {
            "payment": {"entity": {"order_id": order_id}},
            "order": {"entity": {"id": order_id}},
        },
    }


def _failed_event(order_id: str, event_id: str, created_at: int) -> dict:
    return {
        "event": "payment.failed",
        "created_at": created_at,
        "payload": {
            "payment": {"entity": {"order_id": order_id}},
            "order": {"entity": {"id": order_id}},
        },
    }


def test_forged_signature_returns_400(client):
    body = json.dumps({"event": "payment.captured"}).encode()
    resp = client.post(
        "/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": "deadbeef", "X-Razorpay-Event-Id": "evt_1"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_signature"


def test_duplicate_event_processed_once(client, db):
    payment = _make_checkout_payment(db)
    event = _captured_event(payment.razorpay_order_id, "evt_dup", 1_700_000_000)
    body = json.dumps(event).encode()
    headers = {"X-Razorpay-Signature": _sign(body), "X-Razorpay-Event-Id": "evt_dup"}

    resp1 = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "processed"

    resp2 = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_processed"

    db.refresh(payment)
    assert payment.state == "paid"


def test_out_of_order_events_reach_correct_final_state(client, db):
    payment = _make_checkout_payment(db)

    # A later "failed" with an OLDER event timestamp arrives after "paid" with
    # a NEWER timestamp has already landed (simulating network reordering) —
    # the true final state (paid) must win.
    paid_event = _captured_event(payment.razorpay_order_id, "evt_paid", 1_700_000_200)
    paid_body = json.dumps(paid_event).encode()
    client.post(
        "/webhooks/razorpay",
        content=paid_body,
        headers={"X-Razorpay-Signature": _sign(paid_body), "X-Razorpay-Event-Id": "evt_paid"},
    )

    stale_failed_event = _failed_event(payment.razorpay_order_id, "evt_failed_stale", 1_700_000_100)
    stale_body = json.dumps(stale_failed_event).encode()
    resp = client.post(
        "/webhooks/razorpay",
        content=stale_body,
        headers={"X-Razorpay-Signature": _sign(stale_body), "X-Razorpay-Event-Id": "evt_failed_stale"},
    )
    assert resp.status_code == 200

    db.refresh(payment)
    assert payment.state == "paid"


def test_genuine_later_failure_after_paid_is_rejected_by_state_machine(client, db):
    payment = _make_checkout_payment(db)

    paid_event = _captured_event(payment.razorpay_order_id, "evt_paid2", 1_700_000_100)
    paid_body = json.dumps(paid_event).encode()
    client.post(
        "/webhooks/razorpay",
        content=paid_body,
        headers={"X-Razorpay-Signature": _sign(paid_body), "X-Razorpay-Event-Id": "evt_paid2"},
    )

    newer_failed_event = _failed_event(payment.razorpay_order_id, "evt_failed_newer", 1_700_000_300)
    newer_body = json.dumps(newer_failed_event).encode()
    resp = client.post(
        "/webhooks/razorpay",
        content=newer_body,
        headers={"X-Razorpay-Signature": _sign(newer_body), "X-Razorpay-Event-Id": "evt_failed_newer"},
    )
    assert resp.status_code == 200

    # paid is terminal in the state machine; a later failure event cannot
    # move it, so it stays paid rather than silently corrupting state.
    db.refresh(payment)
    assert payment.state == "paid"


def test_razorpay_test_mode_failure_moves_to_failed(client, db):
    payment = _make_checkout_payment(db)
    event = _failed_event(payment.razorpay_order_id, "evt_fail_only", 1_700_000_050)
    body = json.dumps(event).encode()
    resp = client.post(
        "/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": _sign(body), "X-Razorpay-Event-Id": "evt_fail_only"},
    )
    assert resp.status_code == 200
    db.refresh(payment)
    assert payment.state == "failed"

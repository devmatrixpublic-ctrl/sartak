"""Roadmap pillars 1 and 4 (server side): payee fan-in escalation and trusted-contact approve/block."""

from app.db.models import Device, TrustedLink

NONE = {"level": "NONE", "score": 0.0, "reasons": []}
HARD = {"level": "HARD", "score": 2.0, "reasons": ["F_NEW_PAYEE"]}


def _h(device_id):
    return {"Authorization": f"Bearer {device_id}"}


def _risk(client, device_id, payee="mule-payee", method="upi_intent", decision=NONE, is_p2p=True):
    return client.post(
        "/risk-check",
        json={"decision": decision, "method": method, "amount": 500.0, "payee_hash": payee, "is_p2p": is_p2p},
        headers=_h(device_id),
    )


def _link(db, owner, trusted):
    for d in (owner, trusted):
        if db.get(Device, d) is None:
            db.add(Device(id=d, public_key=f"pk-{d}", attestation_level="TEE", verified_boot_state="verified"))
    db.add(TrustedLink(owner_device_id=owner, trusted_device_id=trusted))
    db.commit()


# ---- pillar 1: payee fan-in ----

def test_clean_payment_to_an_ordinary_payee_is_still_allowed(client):
    r = _risk(client, "sender-1", payee="plain-payee")
    assert r.json()["decision"] == "ALLOW"
    assert "hold_reason" not in r.json()


def test_payee_paid_by_three_other_devices_is_held(client):
    for i in range(3):
        assert _risk(client, f"victim-{i}").json()["decision"] == "ALLOW"
    r = _risk(client, "victim-new")
    assert r.status_code == 200
    assert r.json()["decision"] == "HOLD"
    assert r.json()["hold_reason"] == "payee_fan_in"
    assert client.get(f"/payments/{r.json()['payment_id']}", headers=_h("victim-new")).json()["state"] == "held"


def test_busy_merchant_is_never_held_for_fan_in(client):
    for i in range(6):
        assert _risk(client, f"customer-{i}", payee="shop", is_p2p=False).json()["decision"] == "ALLOW"


def test_same_device_repeating_a_payee_is_not_fan_in(client):
    for _ in range(6):
        assert _risk(client, "regular-user", payee="landlord").json()["decision"] == "ALLOW"


def test_two_other_senders_is_below_the_threshold(client):
    _risk(client, "a")
    _risk(client, "b")
    assert _risk(client, "c").json()["decision"] == "ALLOW"


def test_detector_hold_keeps_its_own_reason(client):
    r = _risk(client, "d1", decision=HARD)
    assert r.json()["decision"] == "HOLD"
    assert r.json()["hold_reason"] == "detector"


# ---- pillar 4, rung 4: dual custody ----

def _held(client, db, method="upi_intent"):
    _link(db, "owner", "guardian")
    r = _risk(client, "owner", payee="p-held", method=method, decision=HARD)
    assert r.json()["decision"] == "HOLD"
    return r.json()["payment_id"]


def test_trusted_contact_approves_upi_payment_and_hand_off_starts(client, db):
    pid = _held(client, db)
    r = client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("guardian"))
    assert r.status_code == 200
    assert r.json()["state"] == "handed_off"
    assert client.get(f"/payments/{pid}", headers=_h("owner")).json()["state"] == "handed_off"


def test_trusted_contact_approves_checkout_and_order_is_created(client, db):
    pid = _held(client, db, method="checkout")
    r = client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("guardian"))
    assert r.json()["state"] == "approved"
    assert r.json()["razorpay_order_id"]


def test_trusted_contact_blocks_and_block_is_final(client, db):
    pid = _held(client, db)
    assert client.post(f"/payments/{pid}/decision", json={"decision": "block"}, headers=_h("guardian")).json()["state"] == "blocked"
    again = client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("guardian"))
    assert again.status_code == 409


def test_owner_cannot_approve_their_own_held_payment(client, db):
    pid = _held(client, db)
    r = client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("owner"))
    assert r.status_code == 404
    assert client.get(f"/payments/{pid}", headers=_h("owner")).json()["state"] == "held"


def test_unlinked_stranger_cannot_decide_and_cannot_tell_it_exists(client, db):
    pid = _held(client, db)
    stranger = client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("stranger"))
    missing = client.post("/payments/does-not-exist/decision", json={"decision": "approve"}, headers=_h("stranger"))
    assert stranger.status_code == missing.status_code == 404
    assert stranger.json()["code"] == missing.json()["code"]


def test_only_held_payments_can_be_decided(client, db):
    _link(db, "owner2", "guardian2")
    pid = _risk(client, "owner2", payee="ok-payee").json()["payment_id"]  # ALLOW, handed_off
    r = client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("guardian2"))
    assert r.status_code == 409


def test_unknown_decision_value_and_extra_fields_are_rejected(client, db):
    pid = _held(client, db)
    assert client.post(f"/payments/{pid}/decision", json={"decision": "maybe"}, headers=_h("guardian")).status_code == 422
    assert client.post(f"/payments/{pid}/decision", json={"decision": "approve", "state": "paid"}, headers=_h("guardian")).status_code == 422
    assert client.post(f"/payments/{pid}/decision", json={"decision": "approve"}).status_code == 401


def test_alert_push_carries_the_payment_id(client, db):
    from app.alerts.fcm_client import LocalStubFcmClient
    from app.alerts.service import send_alert

    _link(db, "owner3", "guardian3")
    db.get(Device, "guardian3").fcm_token = "tok"
    db.commit()
    sent = []

    class Spy(LocalStubFcmClient):
        def send(self, token, *, title, body, data=None):
            sent.append(data)

    send_alert(db, owner_device_id="owner3", alert_type="alarm", reasons=["x"], fcm_client=Spy(), payment_id="pay-1")
    assert sent[0]["payment_id"] == "pay-1"

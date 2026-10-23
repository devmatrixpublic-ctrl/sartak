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
    db.add(TrustedLink(owner_device_id=owner, trusted_device_id=trusted, status="accepted"))
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


def test_trusted_contact_approves_checkout_then_owner_fetches_the_order(client, db):
    pid = _held(client, db, method="checkout")
    r = client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("guardian"))
    assert r.json()["state"] == "approved"
    assert "razorpay_order_id" not in r.json()  # the contact's call has no amount, so no order yet
    again = _override(client, "owner", pid, method="checkout", payee="p-held")
    assert again.status_code == 200 and again.json()["order_id"]


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


# ---- "Continue anyway": held -> allowed_by_user ----

def _override(client, device, pid, method="upi_intent", payee="p-ov", amount=500.0):
    return client.post(
        "/risk-check",
        json={"decision": HARD, "method": method, "amount": amount, "payee_hash": payee, "override": True, "payment_id": pid},
        headers=_h(device),
    )


def test_override_releases_a_detector_hold_and_is_recorded(client):
    pid = _risk(client, "ov-1", payee="p-ov", decision=HARD).json()["payment_id"]
    r = _override(client, "ov-1", pid)
    assert r.status_code == 200 and r.json()["decision"] == "ALLOW" and r.json()["payment_id"] == pid
    p = client.get(f"/payments/{pid}", headers=_h("ov-1")).json()
    assert p["state"] == "handed_off" and p["user_override"] is True


def test_override_on_checkout_creates_an_order(client):
    pid = _risk(client, "ov-2", payee="p-ov", method="checkout", decision=HARD).json()["payment_id"]
    r = _override(client, "ov-2", pid, method="checkout")
    assert r.json()["decision"] == "ALLOW" and r.json()["order_id"]


def test_override_needs_a_payment_id_and_the_owner(client):
    pid = _risk(client, "ov-3", payee="p-ov", decision=HARD).json()["payment_id"]
    body = {"decision": HARD, "method": "upi_intent", "amount": 5.0, "payee_hash": "x", "override": True}
    assert client.post("/risk-check", json=body, headers=_h("ov-3")).status_code == 404
    assert _override(client, "someone-else", pid).status_code == 404
    assert client.get(f"/payments/{pid}", headers=_h("ov-3")).json()["state"] == "held"


def test_override_cannot_be_used_twice_or_on_a_fan_in_hold(client):
    pid = _risk(client, "ov-4", payee="p-ov", decision=HARD).json()["payment_id"]
    assert _override(client, "ov-4", pid).status_code == 200
    assert _override(client, "ov-4", pid).status_code == 409
    for i in range(3):
        _risk(client, f"ov-v{i}", payee="mule-ov")
    fan = _risk(client, "ov-5", payee="mule-ov")
    assert fan.json()["hold_reason"] == "payee_fan_in"
    body = {"decision": NONE, "method": "upi_intent", "amount": 500.0, "payee_hash": "mule-ov",
            "override": True, "payment_id": fan.json()["payment_id"]}
    r = client.post("/risk-check", json=body, headers=_h("ov-5"))
    assert r.status_code == 409 and r.json()["code"] == "override_not_allowed"


def test_override_with_wrong_method_is_refused(client):
    pid = _risk(client, "ov-6", payee="p-ov", decision=HARD).json()["payment_id"]
    assert _override(client, "ov-6", pid, method="checkout").status_code == 409


# ---- amount band: the rupee amount is never stored ----

def test_payment_shows_a_band_not_an_amount(client, db):
    from app.db.models import Payment
    pid = _risk(client, "band-1", payee="p-band").json()["payment_id"]  # amount 500.0
    p = client.get(f"/payments/{pid}", headers=_h("band-1")).json()
    assert p["amount_band"] == "500_2k" and "amount" not in p
    assert not hasattr(Payment, "amount")
    assert "amount" not in Payment.__table__.columns


def test_amount_band_edges():
    from app.payments.bands import amount_band
    assert [amount_band(a) for a in (0.01, 499.99, 500, 1999, 2000, 9999, 10000, 49999, 50000, 199999, 200000, 1e7)] == [
        "lt_500", "lt_500", "500_2k", "500_2k", "2k_10k", "2k_10k", "10k_50k", "10k_50k", "50k_2l", "50k_2l", "gt_2l", "gt_2l"]


def test_override_with_an_amount_outside_the_held_band_is_refused(client):
    pid = _risk(client, "band-2", payee="p-band", decision=HARD).json()["payment_id"]
    r = _override(client, "band-2", pid, payee="p-band", amount=900000.0)
    assert r.status_code == 409 and r.json()["code"] == "amount_mismatch"


# ---- silent LOG level (shadow mode) ----

def test_log_level_is_allowed_never_held(client):
    r = _risk(client, "log-1", payee="p-log", decision={"level": "LOG", "score": 9.0, "reasons": ["F_NEW_PAYEE"]})
    assert r.status_code == 200 and r.json()["decision"] == "ALLOW"


# ---- DELETE /device: "Delete my data" ----

def test_delete_device_erases_its_rows_and_only_its_rows(client, db):
    from app.db.models import Alert, Device, Payment, TrustedLink
    _link(db, "gone", "buddy")
    _link(db, "other", "buddy2")
    _risk(client, "gone", payee="p-del")
    _risk(client, "other", payee="p-keep")
    db.add(Alert(device_id="gone", type="alarm"))
    db.commit()
    assert client.delete("/device", headers=_h("gone")).status_code == 204
    db.expire_all()
    assert db.get(Device, "gone") is None
    assert db.query(Payment).filter(Payment.device_id == "gone").count() == 0
    assert db.query(Alert).filter(Alert.device_id == "gone").count() == 0
    assert db.query(TrustedLink).filter(TrustedLink.owner_device_id == "gone").count() == 0
    assert db.get(Device, "buddy") is not None and db.get(Device, "other") is not None
    assert db.query(Payment).filter(Payment.device_id == "other").count() == 1


def test_delete_device_needs_a_token(client):
    assert client.delete("/device").status_code == 401

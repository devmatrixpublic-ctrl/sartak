"""A trusted contact must accept before receiving anything; pending and revoked links get no push."""

from app.alerts.fcm_client import LocalStubFcmClient
from app.alerts.service import ALERT_BODY, send_alert
from app.db.models import Device, TrustedLink

TOKEN = "tok-contact-1234567890"


def _h(d):
    return {"Authorization": f"Bearer {d}"}


def _register(db, *ids):
    for d in ids:
        if db.get(Device, d) is None:
            db.add(Device(id=d, public_key=f"pk-{d}", attestation_level="TEE", verified_boot_state="verified"))
    db.commit()


class Spy(LocalStubFcmClient):
    def __init__(self):
        super().__init__()
        self.sent = []

    def send(self, token, title, body, data):
        self.sent.append((token, title, body, data))
        return "id"


def _ask(client, owner="own", contact="con"):
    return client.post("/trusted-contact", json={"trusted_device_id": contact, "fcm_token": TOKEN}, headers=_h(owner))


def test_new_link_is_pending_and_the_contact_is_asked(client, db):
    _register(db, "own", "con")
    r = _ask(client)
    assert r.status_code == 200 and r.json() == {"linked": True, "status": "pending"}
    assert db.query(TrustedLink).one().status == "pending"


def test_contact_sees_the_request_and_accepts(client, db):
    _register(db, "own", "con")
    _ask(client)
    assert client.get("/trusted-contact/requests", headers=_h("con")).json() == {"requests": [{"owner_device_id": "own"}]}
    r = client.post("/trusted-contact/respond", json={"owner_device_id": "own", "decision": "accept"}, headers=_h("con"))
    assert r.json() == {"linked": True, "status": "accepted"}
    assert client.get("/trusted-contact/requests", headers=_h("con")).json() == {"requests": []}


def test_only_the_asked_device_can_answer(client, db):
    _register(db, "own", "con", "stranger")
    _ask(client)
    for who in ("own", "stranger"):
        r = client.post("/trusted-contact/respond", json={"owner_device_id": "own", "decision": "accept"}, headers=_h(who))
        assert r.status_code == 404
    assert db.query(TrustedLink).one().status == "pending"


def test_decline_revokes_and_accept_cannot_repeat(client, db):
    _register(db, "own", "con")
    _ask(client)
    assert client.post("/trusted-contact/respond", json={"owner_device_id": "own", "decision": "decline"}, headers=_h("con")).json()["status"] == "revoked"
    assert client.post("/trusted-contact/respond", json={"owner_device_id": "own", "decision": "accept"}, headers=_h("con")).status_code == 404
    _ask(client)  # asking again after a decline starts a new pending request
    assert db.query(TrustedLink).one().status == "pending"
    client.post("/trusted-contact/respond", json={"owner_device_id": "own", "decision": "accept"}, headers=_h("con"))
    assert client.post("/trusted-contact/respond", json={"owner_device_id": "own", "decision": "accept"}, headers=_h("con")).status_code == 409


def test_owner_removes_the_contact(client, db):
    _register(db, "own", "con")
    _ask(client)
    client.post("/trusted-contact/respond", json={"owner_device_id": "own", "decision": "accept"}, headers=_h("con"))
    assert client.delete("/trusted-contact/con", headers=_h("own")).json() == {"linked": False, "status": "revoked"}
    assert client.delete("/trusted-contact/nobody", headers=_h("own")).status_code == 404
    assert client.delete("/trusted-contact/con", headers=_h("con")).status_code == 404  # not the owner


def test_cannot_name_yourself(client, db):
    _register(db, "own")
    assert _ask(client, "own", "own").status_code == 422


def _alert(db, status):
    _register(db, "own", "con")
    db.get(Device, "con").fcm_token = TOKEN
    db.add(TrustedLink(owner_device_id="own", trusted_device_id="con", status=status))
    db.commit()
    spy = Spy()
    a = send_alert(db, owner_device_id="own", alert_type="alarm", reasons=["F_NEW_PAYEE", "RULE_X"], fcm_client=spy)
    return a, spy


def test_pending_link_receives_no_push(db):
    a, spy = _alert(db, "pending")
    assert spy.sent == [] and a.delivered is False and a.failure_reason == "trusted_contact_not_accepted"


def test_revoked_link_receives_no_push(db):
    a, spy = _alert(db, "revoked")
    assert spy.sent == [] and a.delivered is False and a.failure_reason == "trusted_contact_not_accepted"


def test_accepted_link_gets_one_short_line_and_no_details(db):
    a, spy = _alert(db, "accepted")
    assert a.delivered is True and len(spy.sent) == 1
    token, title, body, data = spy.sent[0]
    assert body == ALERT_BODY and "\n" not in body and len(body) <= 80
    assert "F_NEW_PAYEE" not in body and "RULE_X" not in body
    assert "http" not in body.lower() and "pin" not in body.lower().split() and "otp" not in body.lower().split()


def test_a_pending_contact_cannot_approve_a_held_payment(client, db):
    _register(db, "own", "con")
    db.add(TrustedLink(owner_device_id="own", trusted_device_id="con", status="pending"))
    db.commit()
    hard = {"level": "HARD", "score": 2.0, "reasons": ["F_NEW_PAYEE"]}
    pid = client.post("/risk-check", json={"decision": hard, "method": "upi_intent", "amount": 500.0, "payee_hash": "p"}, headers=_h("own")).json()["payment_id"]
    assert client.post(f"/payments/{pid}/decision", json={"decision": "approve"}, headers=_h("con")).status_code == 404


def test_request_push_is_one_short_line(client, db, monkeypatch):
    from app.routers import trusted_contact as tc
    assert len(tc.REQUEST_PUSH_BODY) <= 80 and "http" not in tc.REQUEST_PUSH_BODY.lower()

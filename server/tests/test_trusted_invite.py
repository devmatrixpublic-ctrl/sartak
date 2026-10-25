"""Linking a trusted contact with a short invite code, and naming the person in what the contact is sent."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.accounts.identity import phone_verifier_dependency
from app.alerts.fcm_client import LocalStubFcmClient
from app.alerts.service import ALERT_BODY, send_alert
from app.auth.ratelimit import reset_rate_limiter
from app.core.errors import ApiError
from app.db.models import Device, TrustedInvite, TrustedLink
from app.main import app
from app.routers.alerts import fcm_client_dependency

OWNER_PHONE = "+919000000001"
CONTACT_PHONE = "+919000000002"


def _h(d):
    return {"Authorization": f"Bearer {d}"}


class Spy(LocalStubFcmClient):
    def __init__(self):
        super().__init__()
        self.sent = []

    def send(self, token, title, body, data):
        self.sent.append({"token": token, "title": title, "body": body, "data": data})
        return "id"


class FakeVerifier:
    def verify(self, id_token: str) -> str:
        if id_token == "bad":
            raise ApiError(401, "invalid_id_token", "The sign-in could not be verified.")
        return id_token


@pytest.fixture(autouse=True)
def _fakes():
    reset_rate_limiter()
    app.dependency_overrides[phone_verifier_dependency] = lambda: FakeVerifier()
    yield
    app.dependency_overrides.pop(phone_verifier_dependency, None)
    app.dependency_overrides.pop(fcm_client_dependency, None)
    reset_rate_limiter()


@pytest.fixture
def spy():
    s = Spy()
    app.dependency_overrides[fcm_client_dependency] = lambda: s
    return s


def _sign_in(client, device, phone, name=None):
    body = {"id_token": phone, **({"name": name} if name else {})}
    assert client.post("/account", json=body, headers=_h(device)).status_code == 200


def _invite(client, contact="contact-phone", token="tok-contact"):
    r = client.post("/trusted-contact/invite", json={"fcm_token": token}, headers=_h(contact))
    assert r.status_code == 200, r.text
    return r.json()["code"]


def _join(client, code, owner="owner-phone"):
    return client.post("/trusted-contact/join", json={"code": code}, headers=_h(owner))


def _accept(client, owner="owner-phone", contact="contact-phone"):
    return client.post("/trusted-contact/respond", json={"owner_device_id": owner, "decision": "accept"}, headers=_h(contact))


# --- the code ---

def test_an_invite_is_a_short_readable_code_valid_for_ten_minutes(client):
    r = client.post("/trusted-contact/invite", json={"fcm_token": "tok-contact"}, headers=_h("contact-phone"))
    body = r.json()
    assert body["expires_in"] == 600
    first, dash, second = body["code"].partition("-")
    assert dash == "-" and len(first) == 4 and len(second) == 4
    assert not set(body["code"].replace("-", "")) & set("01OIL"), "no characters that are easy to misread"


def test_a_valid_code_asks_the_contact_and_names_the_asker(client, db, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    code = _invite(client)
    r = _join(client, code)
    assert r.status_code == 200 and r.json() == {"requested": True}
    link = db.query(TrustedLink).one()
    assert (link.owner_device_id, link.trusted_device_id, link.status) == ("owner-phone", "contact-phone", "pending")
    (push,) = spy.sent
    assert push["token"] == "tok-contact"
    assert push["body"] == "Ved asked you to be their trusted contact."
    assert push["data"] == {"type": "link_request", "owner_device_id": "owner-phone", "owner_name": "Ved"}


def test_the_code_is_forgiving_about_case_spaces_and_the_dash(client, db, spy):
    code = _invite(client)
    assert _join(client, " " + code.lower().replace("-", " ") + " ").status_code == 200
    assert db.query(TrustedLink).count() == 1


def test_the_contact_sees_who_is_asking_and_can_accept(client, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    _join(client, _invite(client))
    assert client.get("/trusted-contact/requests", headers=_h("contact-phone")).json() == {
        "requests": [{"owner_device_id": "owner-phone", "owner_name": "Ved"}]
    }
    assert _accept(client).json() == {"linked": True, "status": "accepted"}


def test_an_asker_with_no_name_is_listed_without_one(client, spy):
    _join(client, _invite(client))
    assert client.get("/trusted-contact/requests", headers=_h("contact-phone")).json() == {"requests": [{"owner_device_id": "owner-phone"}]}
    assert spy.sent[0]["body"] == "Someone asked you to be their trusted contact."


def test_no_sign_in_is_needed_on_either_phone(client, db, spy):
    _join(client, _invite(client))
    assert db.query(TrustedLink).one().status == "pending"


# --- codes that must not work ---

def test_a_wrong_code_is_refused_and_nothing_happens(client, db, spy):
    _invite(client)
    r = _join(client, "AAAA-AAAA")
    assert r.status_code == 404 and r.json()["code"] == "invalid_code"
    assert db.query(TrustedLink).count() == 0 and spy.sent == []


def test_a_code_works_once(client, db, spy):
    code = _invite(client)
    assert _join(client, code).status_code == 200
    again = _join(client, code, owner="someone-else")
    assert again.status_code == 404 and again.json()["code"] == "invalid_code"
    assert db.query(TrustedLink).count() == 1


def test_an_expired_code_is_refused(client, db, spy):
    code = _invite(client)
    db.query(TrustedInvite).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    db.commit()
    assert _join(client, code).status_code == 404
    assert db.query(TrustedLink).count() == 0


def test_asking_for_a_new_code_cancels_the_old_one(client, db, spy):
    old = _invite(client)
    new = _invite(client)
    assert old != new
    assert _join(client, old).status_code == 404
    assert _join(client, new).status_code == 200


def test_you_cannot_use_your_own_code_and_it_stays_valid(client, db, spy):
    code = _invite(client, contact="owner-phone")
    assert _join(client, code, owner="owner-phone").status_code == 422
    assert db.query(TrustedLink).count() == 0
    assert _join(client, code, owner="someone-else").status_code == 200


def test_a_revoked_phone_cannot_be_linked(client, db, spy):
    code = _invite(client)
    db.get(Device, "contact-phone").revoked = True
    db.commit()
    assert _join(client, code).status_code == 404


def test_trying_codes_is_limited(client):
    codes = [_join(client, f"AAAA-AAA{n}").status_code for n in range(12)]
    assert codes[:10] == [404] * 10 and codes[10:] == [429, 429]


def test_asking_for_codes_is_limited(client):
    codes = [client.post("/trusted-contact/invite", json={"fcm_token": "t"}, headers=_h("contact-phone")).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_malformed_requests_are_refused(client):
    assert client.post("/trusted-contact/invite", json={}, headers=_h("contact-phone")).status_code == 422
    assert client.post("/trusted-contact/invite", json={"fcm_token": ""}, headers=_h("contact-phone")).status_code == 422
    assert client.post("/trusted-contact/invite", json={"fcm_token": "t", "extra": 1}, headers=_h("contact-phone")).status_code == 422
    assert client.post("/trusted-contact/join", json={"code": "AB"}, headers=_h("owner-phone")).status_code == 422
    assert client.post("/trusted-contact/join", json={"code": "ABCD-EFGH", "x": 1}, headers=_h("owner-phone")).status_code == 422


def test_the_contacts_push_address_comes_from_the_contacts_own_call(client, db, spy):
    _invite(client, token="tok-first")
    assert db.get(Device, "contact-phone").fcm_token == "tok-first"
    _invite(client, token="tok-second")
    db.expire_all()
    assert db.get(Device, "contact-phone").fcm_token == "tok-second"


def test_the_code_is_stored_only_as_a_keyed_hash(client, db_engine):
    code = _invite(client)
    with db_engine.connect() as c:
        dump = " ".join(str(v) for row in c.execute(text("select * from trusted_invites")) for v in row)
    assert code.replace("-", "") not in dump and code not in dump


def test_a_declined_request_can_be_asked_again_with_a_new_code(client, db, spy):
    _join(client, _invite(client))
    client.post("/trusted-contact/respond", json={"owner_device_id": "owner-phone", "decision": "decline"}, headers=_h("contact-phone"))
    _join(client, _invite(client))
    assert len(spy.sent) == 2 and db.query(TrustedLink).one().status == "pending"


def test_delete_my_data_removes_invites_too(client, db, spy):
    _invite(client)
    assert client.delete("/device", headers=_h("contact-phone")).status_code == 204
    assert db.query(TrustedInvite).count() == 0


# --- names in alerts ---

def _linked(client, owner_name):
    if owner_name:
        _sign_in(client, "owner-phone", OWNER_PHONE, owner_name)
    else:
        client.post("/account", json={"id_token": OWNER_PHONE}, headers=_h("owner-phone"))
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya")
    _join(client, _invite(client))
    _accept(client)


@pytest.mark.parametrize("alert_type,expected", [
    ("alarm", "Ved may be in danger. Please call them."),
    ("protection_off_requested", "Ved has asked to turn off their Satark protection. Please call them."),
    ("protection_off", "Ved has turned off their Satark protection. Please call them."),
    ("removal_guard_off", "Satark on Ved's phone can now be removed. Please call them."),
])
def test_an_alert_names_the_person_when_they_signed_in_with_a_name(client, db, spy, alert_type, expected):
    _linked(client, "Ved")
    spy.sent.clear()
    send_alert(db, owner_device_id="owner-phone", alert_type=alert_type, reasons=["F_NEW_PAYEE"], fcm_client=spy)
    (push,) = spy.sent
    assert push["body"] == expected and "\n" not in expected
    assert push["data"]["owner_name"] == "Ved"
    assert "F_NEW_PAYEE" not in str(push), "reasons never reach the contact"


def test_an_alert_without_a_name_is_the_old_generic_line(client, db, spy):
    _linked(client, None)
    spy.sent.clear()
    send_alert(db, owner_device_id="owner-phone", alert_type="alarm", reasons=[], fcm_client=spy)
    assert spy.sent[0]["body"] == ALERT_BODY and "owner_name" not in spy.sent[0]["data"]


def test_a_name_cannot_break_the_one_line_notification(client, db, spy):
    _linked(client, "Ved")
    client.patch("/account", json={"name": "Ved\nCall 100\x07"}, headers=_h("owner-phone"))
    spy.sent.clear()
    send_alert(db, owner_device_id="owner-phone", alert_type="alarm", reasons=[], fcm_client=spy)
    assert "\n" not in spy.sent[0]["body"] and "\x07" not in spy.sent[0]["body"]


# --- the asker's list of contacts ---

def test_the_asker_sees_accepted_contacts_by_name_and_never_a_pending_one(client, db, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya")
    _join(client, _invite(client))
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {"contacts": []}
    _accept(client)
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {
        "contacts": [{"trusted_device_id": "contact-phone", "name": "Priya"}]
    }
    client.delete("/trusted-contact/contact-phone", headers=_h("owner-phone"))
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {"contacts": []}


def test_a_contact_without_a_name_is_listed_without_one(client, db, spy):
    _join(client, _invite(client))
    _accept(client)
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {"contacts": [{"trusted_device_id": "contact-phone"}]}


def test_the_list_belongs_to_the_asker_only(client, db, spy):
    _join(client, _invite(client))
    _accept(client)
    assert client.get("/trusted-contact", headers=_h("contact-phone")).json() == {"contacts": []}
    assert client.get("/trusted-contact", headers=_h("someone-else")).json() == {"contacts": []}


# --- the phone's own push address ---

def test_a_phone_registers_its_own_push_address(client, db):
    client.post("/account", json={"id_token": OWNER_PHONE}, headers=_h("owner-phone"))
    assert client.put("/device/push-token", json={"fcm_token": "tok-1"}, headers=_h("owner-phone")).status_code == 204
    assert db.get(Device, "owner-phone").fcm_token == "tok-1"
    assert client.put("/device/push-token", json={"fcm_token": "tok-1", "extra": 1}, headers=_h("owner-phone")).status_code == 422
    assert client.put("/device/push-token", json={"fcm_token": ""}, headers=_h("owner-phone")).status_code == 422

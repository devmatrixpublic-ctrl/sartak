"""Linking a trusted contact by phone number, and naming the person in what the contact is sent."""
import pytest

from app.accounts.identity import phone_verifier_dependency
from app.alerts.fcm_client import LocalStubFcmClient
from app.alerts.service import ALERT_BODY, send_alert
from app.auth.ratelimit import reset_rate_limiter
from app.core.errors import ApiError
from app.db.models import Device, TrustedLink
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


def _sign_in(client, device, phone, name=None, token=None):
    body = {"id_token": phone, **({"name": name} if name else {})}
    assert client.post("/account", json=body, headers=_h(device)).status_code == 200
    if token:
        assert client.put("/device/push-token", json={"fcm_token": token}, headers=_h(device)).status_code == 204


def _link(client, owner="owner-phone", phone=CONTACT_PHONE):
    return client.post("/trusted-contact/by-phone", json={"phone": phone}, headers=_h(owner))


def test_a_known_number_gets_a_pending_request_that_names_the_asker(client, db, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya", token="tok-contact")
    r = _link(client)
    assert r.status_code == 200 and r.json() == {"requested": True}
    link = db.query(TrustedLink).one()
    assert (link.owner_device_id, link.trusted_device_id, link.status) == ("owner-phone", "contact-phone", "pending")
    (push,) = spy.sent
    assert push["token"] == "tok-contact"
    assert push["body"] == "Ved asked you to be their trusted contact."
    assert push["data"] == {"type": "link_request", "owner_device_id": "owner-phone", "owner_name": "Ved"}


def test_the_contact_sees_who_is_asking_and_can_accept(client, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    _sign_in(client, "contact-phone", CONTACT_PHONE, token="tok-contact")
    _link(client)
    assert client.get("/trusted-contact/requests", headers=_h("contact-phone")).json() == {
        "requests": [{"owner_device_id": "owner-phone", "owner_name": "Ved"}]
    }
    r = client.post("/trusted-contact/respond", json={"owner_device_id": "owner-phone", "decision": "accept"}, headers=_h("contact-phone"))
    assert r.json() == {"linked": True, "status": "accepted"}


def test_an_asker_with_no_name_is_still_listed_without_a_name_field(client, spy):
    _sign_in(client, "contact-phone", CONTACT_PHONE, token="tok-contact")
    client.post("/account", json={"id_token": OWNER_PHONE}, headers=_h("owner-phone"))
    _link(client)
    assert client.get("/trusted-contact/requests", headers=_h("contact-phone")).json() == {"requests": [{"owner_device_id": "owner-phone"}]}
    assert spy.sent[0]["body"] == "Someone asked you to be their trusted contact."


def test_an_unknown_number_gets_the_same_answer_and_nothing_happens(client, db, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    known_looking = _link(client, phone="+919000000099")
    assert known_looking.status_code == 200 and known_looking.json() == {"requested": True}
    assert db.query(TrustedLink).count() == 0 and spy.sent == []


def test_a_contact_who_never_registered_a_push_address_cannot_be_reached_yet(client, db, spy):
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya")
    r = _link(client)
    assert r.json() == {"requested": True}
    assert db.query(TrustedLink).count() == 0 and spy.sent == []


def test_you_cannot_ask_your_own_number(client, db, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved", token="tok-owner")
    assert _link(client, phone=OWNER_PHONE).json() == {"requested": True}
    assert db.query(TrustedLink).count() == 0


def test_the_newest_phone_on_the_account_is_asked(client, db, spy):
    _sign_in(client, "contact-old", CONTACT_PHONE, "Priya", token="tok-old")
    _sign_in(client, "contact-new", CONTACT_PHONE, "Priya", token="tok-new")
    db.get(Device, "contact-new").created_at = db.get(Device, "contact-old").created_at.replace(year=2099)
    db.commit()
    _link(client)
    assert db.query(TrustedLink).one().trusted_device_id == "contact-new"
    assert spy.sent[0]["token"] == "tok-new"


def test_asking_twice_does_not_push_twice_but_a_declined_request_can_be_asked_again(client, db, spy):
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya", token="tok-contact")
    _link(client)
    _link(client)
    assert len(spy.sent) == 1 and db.query(TrustedLink).count() == 1
    client.post("/trusted-contact/respond", json={"owner_device_id": "owner-phone", "decision": "decline"}, headers=_h("contact-phone"))
    _link(client)
    assert len(spy.sent) == 2 and db.query(TrustedLink).one().status == "pending"


def test_a_revoked_phone_is_not_asked(client, db, spy):
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya", token="tok-contact")
    db.get(Device, "contact-phone").revoked = True
    db.commit()
    _link(client)
    assert db.query(TrustedLink).count() == 0 and spy.sent == []


def test_lookups_are_limited_so_numbers_cannot_be_guessed(client):
    codes = [_link(client, phone=f"+91900000{n:04d}").status_code for n in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_a_malformed_number_is_refused(client):
    for bad in ("9876543210", "+91 98765", "", "+0123456789"):
        assert _link(client, phone=bad).status_code == 422
    assert client.post("/trusted-contact/by-phone", json={"phone": OWNER_PHONE, "x": 1}, headers=_h("owner-phone")).status_code == 422


def test_the_number_asked_about_is_not_kept(client, db_engine, spy):
    from sqlalchemy import text

    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya", token="tok-contact")
    _link(client)
    with db_engine.connect() as c:
        for table in ("trusted_links", "devices", "alerts"):
            dump = " ".join(str(v) for row in c.execute(text(f"select * from {table}")) for v in row)
            assert "9000000002" not in dump, table


# --- names in alerts ---

def _accepted(client, db, owner_name):
    _sign_in(client, "owner-phone", OWNER_PHONE, owner_name)
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya", token="tok-contact")
    _link(client)
    client.post("/trusted-contact/respond", json={"owner_device_id": "owner-phone", "decision": "accept"}, headers=_h("contact-phone"))


@pytest.mark.parametrize("alert_type,expected", [
    ("alarm", "Ved may be in danger. Please call them."),
    ("protection_off_requested", "Ved has asked to turn off their Satark protection. Please call them."),
    ("protection_off", "Ved has turned off their Satark protection. Please call them."),
    ("removal_guard_off", "Satark on Ved's phone can now be removed. Please call them."),
])
def test_an_alert_names_the_person_when_they_signed_in_with_a_name(client, db, spy, alert_type, expected):
    _accepted(client, db, "Ved")
    spy.sent.clear()
    send_alert(db, owner_device_id="owner-phone", alert_type=alert_type, reasons=["F_NEW_PAYEE"], fcm_client=spy)
    (push,) = spy.sent
    assert push["body"] == expected and "\n" not in expected
    assert push["data"]["owner_name"] == "Ved"
    assert "F_NEW_PAYEE" not in str(push), "reasons never reach the contact"


def test_an_alert_without_a_name_is_the_old_generic_line(client, db, spy):
    _accepted(client, db, None)
    spy.sent.clear()
    send_alert(db, owner_device_id="owner-phone", alert_type="alarm", reasons=[], fcm_client=spy)
    assert spy.sent[0]["body"] == ALERT_BODY and "owner_name" not in spy.sent[0]["data"]


def test_a_name_cannot_break_the_one_line_notification(client, db, spy):
    _accepted(client, db, "Ved")
    client.patch("/account", json={"name": "Ved\nCall 100\x07"}, headers=_h("owner-phone"))
    spy.sent.clear()
    send_alert(db, owner_device_id="owner-phone", alert_type="alarm", reasons=[], fcm_client=spy)
    assert "\n" not in spy.sent[0]["body"] and "\x07" not in spy.sent[0]["body"]


# --- the phone's own push address ---

def test_a_phone_registers_its_own_push_address(client, db):
    client.post("/account", json={"id_token": OWNER_PHONE}, headers=_h("owner-phone"))
    assert client.put("/device/push-token", json={"fcm_token": "tok-1"}, headers=_h("owner-phone")).status_code == 204
    assert db.get(Device, "owner-phone").fcm_token == "tok-1"
    assert client.put("/device/push-token", json={"fcm_token": "tok-1", "extra": 1}, headers=_h("owner-phone")).status_code == 422
    assert client.put("/device/push-token", json={"fcm_token": ""}, headers=_h("owner-phone")).status_code == 422


# --- the asker's list of contacts ---

def test_the_asker_sees_accepted_contacts_by_name_and_never_a_pending_one(client, db, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya", token="tok-contact")
    _link(client)
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {"contacts": []}, "pending must look like nothing"
    client.post("/trusted-contact/respond", json={"owner_device_id": "owner-phone", "decision": "accept"}, headers=_h("contact-phone"))
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {
        "contacts": [{"trusted_device_id": "contact-phone", "name": "Priya"}]
    }
    client.delete("/trusted-contact/contact-phone", headers=_h("owner-phone"))
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {"contacts": []}


def test_a_contact_without_a_name_is_listed_without_one(client, db, spy):
    client.post("/account", json={"id_token": OWNER_PHONE}, headers=_h("owner-phone"))
    _sign_in(client, "contact-phone", CONTACT_PHONE, token="tok-contact")
    _link(client)
    client.post("/trusted-contact/respond", json={"owner_device_id": "owner-phone", "decision": "accept"}, headers=_h("contact-phone"))
    assert client.get("/trusted-contact", headers=_h("owner-phone")).json() == {"contacts": [{"trusted_device_id": "contact-phone"}]}


def test_the_list_belongs_to_the_asker_only(client, db, spy):
    _sign_in(client, "owner-phone", OWNER_PHONE, "Ved")
    _sign_in(client, "contact-phone", CONTACT_PHONE, "Priya", token="tok-contact")
    _link(client)
    client.post("/trusted-contact/respond", json={"owner_device_id": "owner-phone", "decision": "accept"}, headers=_h("contact-phone"))
    assert client.get("/trusted-contact", headers=_h("contact-phone")).json() == {"contacts": []}
    assert client.get("/trusted-contact", headers=_h("someone-else")).json() == {"contacts": []}

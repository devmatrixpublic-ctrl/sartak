from app.alerts.fcm_client import LocalStubFcmClient
from app.alerts.service import send_alert
from app.db.models import Device, TrustedLink

OWNER = {"Authorization": "Bearer owner-device"}


def _link(db, owner_id="owner-device", trusted_id="trusted-device", fcm_token="tok-good"):
    db.add(Device(id=owner_id, public_key=f"pk-{owner_id}", attestation_level="TEE", verified_boot_state="verified"))
    db.add(
        Device(
            id=trusted_id,
            public_key=f"pk-{trusted_id}",
            attestation_level="TEE",
            verified_boot_state="verified",
            fcm_token=fcm_token,
        )
    )
    db.add(TrustedLink(owner_device_id=owner_id, trusted_device_id=trusted_id, status="accepted"))
    db.commit()


def test_stale_token_returns_delivered_false_and_logs(db):
    _link(db, fcm_token="tok-stale")
    client = LocalStubFcmClient(invalid_tokens=frozenset({"tok-stale"}))

    alert = send_alert(
        db,
        owner_device_id="owner-device",
        alert_type="alarm",
        reasons=["unknown_contact"],
        fcm_client=client,
    )

    assert alert.delivered is False
    assert "stale" in alert.failure_reason


def test_stale_token_over_http_returns_2xx(client, db):
    _link(db, fcm_token="tok-stale")

    import app.routers.alerts as alerts_router

    stale_client = LocalStubFcmClient(invalid_tokens=frozenset({"tok-stale"}))
    client.app.dependency_overrides[alerts_router.fcm_client_dependency] = lambda: stale_client

    resp = client.post(
        "/alert",
        json={"device_id": "owner-device", "type": "alarm", "reasons": ["unknown_contact"]},
        headers=OWNER,
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True
    client.app.dependency_overrides.pop(alerts_router.fcm_client_dependency, None)


def test_push_delivered_for_valid_token(db):
    _link(db, fcm_token="tok-good")
    client = LocalStubFcmClient()

    alert = send_alert(
        db,
        owner_device_id="owner-device",
        alert_type="long_session",
        reasons=["unknown_video_2h"],
        fcm_client=client,
    )

    assert alert.delivered is True
    assert alert.failure_reason is None


def test_alert_with_no_trusted_contact_is_2xx_and_logged(db):
    db.add(Device(id="lonely-device", public_key="pk-lonely", attestation_level="TEE", verified_boot_state="verified"))
    db.commit()
    client = LocalStubFcmClient()

    alert = send_alert(
        db,
        owner_device_id="lonely-device",
        alert_type="alarm",
        reasons=[],
        fcm_client=client,
    )
    assert alert.delivered is False
    assert alert.failure_reason == "no_trusted_contact_linked"


def test_alert_cannot_be_raised_for_another_device(client, db):
    _link(db)
    resp = client.post(
        "/alert",
        json={"device_id": "someone-else", "type": "alarm", "reasons": []},
        headers=OWNER,
    )
    assert resp.status_code == 403


def test_trusted_contact_must_already_be_registered(client):
    resp = client.post(
        "/trusted-contact",
        json={"trusted_device_id": "never-registered", "fcm_token": "tok-xyz"},
        headers=OWNER,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "trusted_device_not_found"


def test_trusted_contact_link_endpoint(client, db):
    db.add(Device(id="trusted-device-2", public_key="pk-trusted-2", attestation_level="TEE",
                  verified_boot_state="verified"))
    db.commit()
    resp = client.post(
        "/trusted-contact",
        json={"trusted_device_id": "trusted-device-2", "fcm_token": "tok-xyz"},
        headers=OWNER,
    )
    assert resp.status_code == 200
    assert resp.json()["linked"] is True


class _Recorder:
    """A push client that keeps what it was asked to send."""

    def __init__(self):
        self.sent = []

    def send(self, token, title, body, data):
        self.sent.append({"token": token, "title": title, "body": body, "data": data})
        return "recorded"


import pytest  # noqa: E402

from app.alerts.service import ALERT_BODY  # noqa: E402

PROTECTION_ALERTS = {
    "protection_off_requested": "Someone you protect has asked to turn off their Satark protection. Please call them.",
    "protection_off": "Someone you protect has turned off their Satark protection. Please call them.",
    "removal_guard_off": "Satark on a phone you protect can now be removed. Please call them.",
}


@pytest.mark.parametrize("alert_type,text", PROTECTION_ALERTS.items())
def test_switching_protection_off_tells_the_accepted_contact_in_one_plain_line(db, alert_type, text):
    _link(db)
    rec = _Recorder()
    alert = send_alert(db, owner_device_id="owner-device", alert_type=alert_type, reasons=[], fcm_client=rec)
    assert alert.delivered is True
    assert len(rec.sent) == 1
    sent = rec.sent[0]
    assert sent["body"] == text
    assert sent["data"] == {"type": alert_type, "owner_device_id": "owner-device"}  # no payment, reason or name


def test_ordinary_alarms_keep_the_original_line(db):
    _link(db)
    rec = _Recorder()
    send_alert(db, owner_device_id="owner-device", alert_type="alarm", reasons=["unknown_contact"], fcm_client=rec)
    assert rec.sent[0]["body"] == ALERT_BODY


@pytest.mark.parametrize("alert_type", PROTECTION_ALERTS)
def test_protection_alerts_are_accepted_over_http_and_unknown_types_are_not(client, db, alert_type):
    _link(db)
    ok = client.post("/alert", json={"device_id": "owner-device", "type": alert_type}, headers=OWNER)
    assert ok.status_code == 200 and ok.json()["accepted"] is True
    bad = client.post("/alert", json={"device_id": "owner-device", "type": "made_up"}, headers=OWNER)
    assert bad.status_code == 422


def test_a_contact_who_has_not_accepted_gets_no_protection_alert(db):
    db.add(Device(id="owner-device", public_key="pk-o", attestation_level="TEE", verified_boot_state="verified"))
    db.add(Device(id="trusted-device", public_key="pk-t", attestation_level="TEE", verified_boot_state="verified", fcm_token="tok"))
    db.add(TrustedLink(owner_device_id="owner-device", trusted_device_id="trusted-device", status="pending"))
    db.commit()
    rec = _Recorder()
    alert = send_alert(db, owner_device_id="owner-device", alert_type="protection_off", reasons=[], fcm_client=rec)
    assert alert.delivered is False and rec.sent == []

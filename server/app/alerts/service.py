import logging

from sqlalchemy.orm import Session

from app.accounts.identity import display_name
from app.alerts.fcm_client import FcmClient, FcmTokenInvalid
from app.db.models import Alert, Device, TrustedLink

logger = logging.getLogger("satark.alerts.service")

ALERT_TITLES = {
    "alarm": "Satark alert",
    "long_session": "Satark alert",
    "protection_off_requested": "Satark alert",
    "protection_off": "Satark alert",
    "removal_guard_off": "Satark alert",
}

# ONE short line for every alert: no reasons, amounts, payees or names reach the contact's lock screen.
ALERT_BODY = "Someone you protect may be in danger. Please call them."
# Someone switching Satark off, or making it removable, is what a scammer on the phone asks for: say that, in one line.
ALERT_BODIES = {
    "protection_off_requested": "Someone you protect has asked to turn off their Satark protection. Please call them.",
    "protection_off": "Someone you protect has turned off their Satark protection. Please call them.",
    "removal_guard_off": "Satark on a phone you protect can now be removed. Please call them.",
}
# The same lines with the person's name, for someone who signed in. Still one line, and still nothing about amounts or payees.
NAMED_ALERT_BODY = "{name} may be in danger. Please call them."
NAMED_ALERT_BODIES = {
    "protection_off_requested": "{name} has asked to turn off their Satark protection. Please call them.",
    "protection_off": "{name} has turned off their Satark protection. Please call them.",
    "removal_guard_off": "Satark on {name}'s phone can now be removed. Please call them.",
}


def send_alert(
    db: Session,
    *,
    owner_device_id: str,
    alert_type: str,
    reasons: list[str],
    fcm_client: FcmClient,
    payment_id: str | None = None,
) -> Alert:
    # Only a contact who accepted gets anything; pending and revoked links receive nothing.
    link = (
        db.query(TrustedLink)
        .filter(TrustedLink.owner_device_id == owner_device_id, TrustedLink.status == "accepted")
        .order_by(TrustedLink.created_at.desc())
        .first()
    )
    alert = Alert(device_id=owner_device_id, type=alert_type, delivered=False)

    if link is None:
        any_link = db.query(TrustedLink).filter(TrustedLink.owner_device_id == owner_device_id).first()
        alert.failure_reason = "no_trusted_contact_linked" if any_link is None else "trusted_contact_not_accepted"
        logger.warning("alert_no_trusted_contact", extra={"owner_device_id": owner_device_id})
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    trusted_device = db.get(Device, link.trusted_device_id)

    if trusted_device is None or not trusted_device.fcm_token:
        alert.failure_reason = "trusted_device_has_no_fcm_token"
        logger.warning("alert_no_fcm_token", extra={"owner_device_id": owner_device_id})
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    title = ALERT_TITLES.get(alert_type, "Satark alert")
    name = display_name(db, owner_device_id)
    if name:
        body = NAMED_ALERT_BODIES.get(alert_type, NAMED_ALERT_BODY).format(name=name)
    else:
        body = ALERT_BODIES.get(alert_type, ALERT_BODY)

    try:
        fcm_client.send(
            trusted_device.fcm_token,
            title=title,
            body=body,
            data={
                "type": alert_type,
                "owner_device_id": owner_device_id,
                **({"owner_name": name} if name else {}),
                **({"payment_id": payment_id} if payment_id else {}),
            },
        )
        alert.delivered = True
    except FcmTokenInvalid as exc:
        # A stale token is an expected, routine failure mode: log it, store
        # the alert as undelivered, and still return 2xx to the caller.
        alert.failure_reason = f"stale_fcm_token: {exc}"
        logger.warning(
            "alert_stale_fcm_token",
            extra={"owner_device_id": owner_device_id, "trusted_device_id": trusted_device.id},
        )

    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert

import logging

from sqlalchemy.orm import Session

from app.alerts.fcm_client import FcmClient, FcmTokenInvalid
from app.db.models import Alert, Device, TrustedLink

logger = logging.getLogger("satark.alerts.service")

ALERT_TITLES = {
    "alarm": "Satark alert",
    "long_session": "Long unknown-origin session",
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
    link = (
        db.query(TrustedLink)
        .filter(TrustedLink.owner_device_id == owner_device_id)
        .order_by(TrustedLink.created_at.desc())
        .first()
    )
    alert = Alert(device_id=owner_device_id, type=alert_type, delivered=False)

    if link is None:
        alert.failure_reason = "no_trusted_contact_linked"
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
    body = "; ".join(reasons[:3]) if reasons else "Review your device."

    try:
        fcm_client.send(
            trusted_device.fcm_token,
            title=title,
            body=body,
            data={
                "type": alert_type,
                "owner_device_id": owner_device_id,
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

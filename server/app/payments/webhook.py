"""Razorpay webhook handling: signature verification, dedupe, out-of-order resolution."""

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Payment, WebhookEvent
from app.payments.state_machine import can_transition

logger = logging.getLogger("satark.payments.webhook")

# Razorpay event types this handler acts on; everything else is accepted
# and ignored (2xx) so Razorpay doesn't retry it forever.
SUCCESS_EVENTS = {"payment.captured", "order.paid"}
FAILURE_EVENTS = {"payment.failed"}


class ForgedSignature(Exception):
    pass


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def record_event_once(db: Session, event_id: str, raw_body: bytes) -> bool:
    """Insert the event id; returns True if this is the first time we've seen it."""
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    db.add(WebhookEvent(event_id=event_id, payload_hash=payload_hash))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _extract_order_id(payload: dict) -> str | None:
    entities = payload.get("payload", {})
    order_entity = entities.get("order", {}).get("entity", {})
    if order_entity.get("id"):
        return order_entity["id"]
    payment_entity = entities.get("payment", {}).get("entity", {})
    return payment_entity.get("order_id")


def apply_webhook_event(db: Session, payload: dict) -> None:
    event_type = payload.get("event", "")
    order_id = _extract_order_id(payload)
    event_created_at_raw = payload.get("created_at")
    event_created_at = (
        datetime.fromtimestamp(event_created_at_raw, tz=timezone.utc)
        if isinstance(event_created_at_raw, (int, float))
        else datetime.now(timezone.utc)
    )

    if event_type not in SUCCESS_EVENTS and event_type not in FAILURE_EVENTS:
        logger.info("webhook_event_ignored", extra={"event_type": event_type})
        return

    if not order_id:
        logger.warning("webhook_event_missing_order_id", extra={"event_type": event_type})
        return

    payment = db.query(Payment).filter(Payment.razorpay_order_id == order_id).one_or_none()
    if payment is None:
        logger.warning("webhook_event_unknown_order", extra={"order_id": order_id})
        return

    # Out-of-order protection: ignore an event older than the last one we
    # already applied to this payment (e.g. a delayed retry of a stale
    # failure arriving after a later success was already recorded).
    if payment.last_webhook_event_at is not None:
        last = payment.last_webhook_event_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if event_created_at <= last:
            logger.info(
                "webhook_event_stale_ignored",
                extra={"payment_id": payment.id, "event_type": event_type},
            )
            return

    target = "paid" if event_type in SUCCESS_EVENTS else "failed"

    if payment.state == target:
        payment.last_webhook_event_at = event_created_at
        db.commit()
        return

    if not can_transition(payment.method, payment.state, target):
        logger.warning(
            "webhook_event_invalid_transition",
            extra={"payment_id": payment.id, "from_state": payment.state, "target": target},
        )
        return

    payment.state = target
    payment.last_webhook_event_at = event_created_at
    db.commit()

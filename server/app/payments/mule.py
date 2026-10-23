"""Receiver-side mule signal: how many different devices paid this payee recently.

A coached-scam payee is a collection account, so it receives from many unrelated victims in a short time.
The on-device detector only sees the sender's side; this adds the receiver's. Counts are over `payee_hash`
(already hashed on the phone) and never leave the database.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Payment


def payee_distinct_other_senders(db: Session, *, payee_hash: str, device_id: str, window_minutes: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    return db.scalar(
        select(func.count(func.distinct(Payment.device_id))).where(
            Payment.payee_hash == payee_hash,
            Payment.device_id != device_id,
            Payment.created_at >= cutoff,
        )
    ) or 0


def is_mule_fan_in(db: Session, *, payee_hash: str, device_id: str, threshold: int, window_minutes: int) -> bool:
    if threshold <= 0:
        return False
    return payee_distinct_other_senders(
        db, payee_hash=payee_hash, device_id=device_id, window_minutes=window_minutes
    ) >= threshold

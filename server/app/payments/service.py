from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Payment, TrustedLink
from app.payments.bands import amount_band
from app.payments.order_client import OrderClient
from app.payments.state_machine import require_transition

DEFAULT_HANDED_OFF_TIMEOUT_SECONDS = 15 * 60


def create_payment(
    db: Session,
    *,
    device_id: str,
    method: str,
    amount: float,
    payee_hash: str,
    risk_decision: str,
    order_client: OrderClient,
    hold_reason: str | None = None,
) -> Payment:
    """Create a payment from a risk-check decision (HOLD or ALLOW)."""
    state = "held" if risk_decision == "HOLD" else "allowed"
    require_transition(method, "created", state)

    payment = Payment(
        device_id=device_id,
        method=method,
        amount_band=amount_band(amount),
        payee_hash=payee_hash,
        state=state,
        hold_reason=(hold_reason or "detector") if state == "held" else None,
    )

    if state == "allowed" and method == "checkout":
        payment.razorpay_order_id = order_client.create_order(
            amount=amount, currency="INR", receipt=f"satark_{device_id[:8]}"
        )
    elif state == "allowed" and method == "upi_intent":
        # ALLOW for upi_intent means the client launches the UPI chooser
        # immediately — there is no separate "I launched it" callback, so
        # the hand-off starts here, and the timeout clock starts now.
        require_transition(method, "allowed", "handed_off")
        payment.state = "handed_off"
        payment.handed_off_at = datetime.now(timezone.utc)

    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def decide_held_payment(
    db: Session,
    payment: Payment,
    *,
    decider_device_id: str,
    decision: str,
    order_client: OrderClient,
) -> Payment:
    """Dual custody: a held payment is released or blocked only by a device its owner linked as a trusted contact.

    A caller who is not the owner's trusted contact gets the same 404 as an unknown payment (no existence leak).
    Approving a upi_intent payment starts the hand-off, as ALLOW does; approving a checkout leaves the order to the owner.
    """
    linked = db.query(TrustedLink).filter(
        TrustedLink.owner_device_id == payment.device_id,
        TrustedLink.trusted_device_id == decider_device_id,
        TrustedLink.status == "accepted",
    ).first()
    if linked is None:
        raise ApiError(404, "not_found", "Payment not found")

    target = "approved" if decision == "approve" else "blocked"
    require_transition(payment.method, payment.state, target)
    payment.state = target
    payment.decided_by_device_id = decider_device_id
    payment.decided_at = datetime.now(timezone.utc)

    # A checkout approval creates no order here: the amount is not stored, so the owner's app asks for the order
    # (POST /risk-check override) and sends the amount again. A upi_intent approval starts the hand-off.
    if target == "approved" and payment.method == "upi_intent":
        require_transition(payment.method, "approved", "handed_off")
        payment.state = "handed_off"
        payment.handed_off_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(payment)
    return payment


def override_hold(db: Session, payment: Payment, *, order_client: OrderClient, amount: float) -> Payment:
    """The owner chose "Continue anyway" on a detector hold: held -> allowed_by_user, recorded and persisted.

    Only the detector's own hold can be overridden by the person; a hold caused by other devices' payments to the
    same payee (payee_fan_in) is evidence the person's phone cannot see, so it is not theirs to waive.
    """
    if amount_band(amount) != payment.amount_band:
        raise ApiError(409, "amount_mismatch", "The amount does not match the held payment.")
    if payment.method == "checkout" and payment.state == "approved" and payment.razorpay_order_id is None:
        # Trusted contact already approved: this call only creates the order (the owner's app knows the amount).
        payment.razorpay_order_id = order_client.create_order(
            amount=amount, currency="INR", receipt=f"satark_{payment.device_id[:8]}"
        )
        db.commit()
        db.refresh(payment)
        return payment
    if payment.hold_reason != "detector":
        raise ApiError(409, "override_not_allowed", "This hold cannot be overridden from the app.")
    require_transition(payment.method, payment.state, "allowed_by_user")
    payment.state = "allowed_by_user"
    payment.user_override_at = datetime.now(timezone.utc)

    if payment.method == "checkout":
        payment.razorpay_order_id = order_client.create_order(
            amount=amount, currency="INR", receipt=f"satark_{payment.device_id[:8]}"
        )
    else:
        require_transition(payment.method, "allowed_by_user", "handed_off")
        payment.state = "handed_off"
        payment.handed_off_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(payment)
    return payment


def mark_handed_off(db: Session, payment: Payment) -> Payment:
    require_transition(payment.method, payment.state, "handed_off")
    payment.state = "handed_off"
    payment.handed_off_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(payment)
    return payment


def report_result(db: Session, payment: Payment, status: str, txn_ref: str | None) -> Payment:
    if payment.method != "upi_intent":
        raise ApiError(409, "invalid_method", "Only upi_intent payments accept a reported result.")

    target = "reported_success" if status == "success" else "reported_failure"
    require_transition(payment.method, payment.state, target)

    payment.state = target
    payment.reported_status = status
    payment.reported_txn_ref = txn_ref
    db.commit()
    db.refresh(payment)
    return payment


def finalize_checkout(db: Session, payment: Payment, outcome: str) -> Payment:
    """outcome is 'paid' or 'failed', driven only by a verified Razorpay webhook."""
    require_transition(payment.method, payment.state, outcome)
    payment.state = outcome
    db.commit()
    db.refresh(payment)
    return payment


def sweep_stale_handed_off(db: Session, *, ttl_seconds: int = DEFAULT_HANDED_OFF_TIMEOUT_SECONDS) -> int:
    """Move stale upi_intent payments stuck in handed_off to no_result.

    Called by a periodic background job, and opportunistically whenever a
    payment is read, so state is correct even if the service was asleep
    (Render free-tier cold start) while the timeout elapsed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    stale = db.scalars(
        select(Payment).where(
            Payment.method == "upi_intent",
            Payment.state == "handed_off",
            Payment.handed_off_at.is_not(None),
            Payment.handed_off_at < cutoff,
        )
    ).all()
    for payment in stale:
        payment.state = "no_result"
    if stale:
        db.commit()
    return len(stale)


def sweep_if_stale(db: Session, payment: Payment, *, ttl_seconds: int = DEFAULT_HANDED_OFF_TIMEOUT_SECONDS) -> Payment:
    """Evaluate the timeout for a single payment being read, so GET /payments/{id} is correct on wake."""
    if payment.method == "upi_intent" and payment.state == "handed_off" and payment.handed_off_at:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
        handed_off_at = payment.handed_off_at
        if handed_off_at.tzinfo is None:
            handed_off_at = handed_off_at.replace(tzinfo=timezone.utc)
        if handed_off_at < cutoff:
            payment.state = "no_result"
            db.commit()
            db.refresh(payment)
    return payment

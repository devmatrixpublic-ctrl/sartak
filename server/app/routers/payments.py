from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Literal, Optional

from app.auth.dependencies import require_device
from app.core.errors import ApiError
from app.core.schemas import StrictInput
from app.db.models import Payment
from app.db.session import get_db
from app.core.settings import get_settings
from app.payments.order_client import get_order_client
from app.payments.service import decide_held_payment, report_result, sweep_if_stale

router = APIRouter(tags=["payments"])


class PaymentOut(BaseModel):
    id: str
    method: str
    state: str
    amount_band: str
    payee_hash: str
    razorpay_order_id: Optional[str] = None
    hold_reason: Optional[str] = None
    user_override: Optional[bool] = None
    reported_status: Optional[str] = None
    reported_txn_ref: Optional[str] = None

    @classmethod
    def from_model(cls, payment: Payment) -> "PaymentOut":
        return cls(
            id=payment.id,
            method=payment.method,
            state=payment.state,
            amount_band=payment.amount_band,
            payee_hash=payment.payee_hash,
            razorpay_order_id=payment.razorpay_order_id,
            hold_reason=payment.hold_reason,
            user_override=True if payment.user_override_at else None,
            reported_status=payment.reported_status,
            reported_txn_ref=payment.reported_txn_ref,
        )


class PaymentResultIn(StrictInput):
    status: Literal["success", "failure"]
    txn_ref: Optional[str] = Field(default=None, max_length=128)


class PaymentDecisionIn(StrictInput):
    decision: Literal["approve", "block"]


def _get_owned_payment(db: Session, payment_id: str, device_id: str) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.device_id != device_id:
        # Same response for "not found" and "not yours" — do not leak existence (IDOR).
        raise ApiError(404, "not_found", "Payment not found")
    return payment


@router.get("/payments/{payment_id}", response_model=PaymentOut, response_model_exclude_none=True)
async def get_payment(
    payment_id: str,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
) -> PaymentOut:
    payment = _get_owned_payment(db, payment_id, device_id)
    payment = sweep_if_stale(db, payment)
    return PaymentOut.from_model(payment)


@router.post("/payments/{payment_id}/result", response_model=PaymentOut, response_model_exclude_none=True)
async def post_payment_result(
    payment_id: str,
    body: PaymentResultIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
) -> PaymentOut:
    payment = _get_owned_payment(db, payment_id, device_id)
    payment = report_result(db, payment, body.status, body.txn_ref)
    return PaymentOut.from_model(payment)


@router.post("/payments/{payment_id}/decision", response_model=PaymentOut, response_model_exclude_none=True)
async def post_payment_decision(
    payment_id: str,
    body: PaymentDecisionIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
) -> PaymentOut:
    """Trusted-contact approve/block of a held payment (dual custody)."""
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise ApiError(404, "not_found", "Payment not found")
    payment = decide_held_payment(
        db,
        payment,
        decider_device_id=device_id,
        decision=body.decision,
        order_client=get_order_client(get_settings()),
    )
    return PaymentOut.from_model(payment)

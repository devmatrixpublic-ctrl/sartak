from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_device
from app.core.settings import get_settings
from app.db.session import get_db
from app.payments.mule import is_mule_fan_in
from app.payments.order_client import get_order_client
from app.payments.service import create_payment
from app.schemas import RiskCheckRequest, RiskCheckResponse

router = APIRouter(tags=["risk"])


@router.post("/risk-check", response_model=RiskCheckResponse, response_model_exclude_none=True)
async def post_risk_check(
    body: RiskCheckRequest,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
) -> RiskCheckResponse:
    # Baseline server-side policy: HARD and TRUSTED_CONTACT levels from the
    # on-device detector hold the payment; NONE/NUDGE allow it. This is the
    # authoritative decision point — the client cannot self-report ALLOW.
    risk_decision = "HOLD" if body.decision.level in ("HARD", "TRUSTED_CONTACT") else "ALLOW"
    settings = get_settings()
    hold_reason = "detector" if risk_decision == "HOLD" else None
    # Receiver side: a payee that many other devices paid within the hour looks like a collection account.
    # This can only escalate ALLOW to HOLD, never the other way.
    if risk_decision == "ALLOW" and is_mule_fan_in(
        db,
        payee_hash=body.payee_hash,
        device_id=device_id,
        threshold=settings.mule_fanin_threshold,
        window_minutes=settings.mule_fanin_window_minutes,
    ):
        risk_decision, hold_reason = "HOLD", "payee_fan_in"
    order_client = get_order_client(settings)

    payment = create_payment(
        db,
        device_id=device_id,
        method=body.method,
        amount=body.amount,
        payee_hash=body.payee_hash,
        risk_decision=risk_decision,
        order_client=order_client,
        hold_reason=hold_reason,
    )

    return RiskCheckResponse(
        decision=risk_decision,
        payment_id=payment.id,
        order_id=payment.razorpay_order_id,
        hold_reason=payment.hold_reason,
    )

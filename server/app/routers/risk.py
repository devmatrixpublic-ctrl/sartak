from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_device
from app.core.settings import get_settings
from app.db.session import get_db
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
    order_client = get_order_client(get_settings())

    payment = create_payment(
        db,
        device_id=device_id,
        method=body.method,
        amount=body.amount,
        payee_hash=body.payee_hash,
        risk_decision=risk_decision,
        order_client=order_client,
    )

    return RiskCheckResponse(
        decision=risk_decision,
        payment_id=payment.id,
        order_id=payment.razorpay_order_id,
    )

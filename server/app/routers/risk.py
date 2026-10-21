import uuid

from fastapi import APIRouter

from app.schemas import RiskCheckRequest, RiskCheckResponse

router = APIRouter(tags=["risk"])


# SATARK_STUB: always ALLOW. Member 1 swaps this for the real risk engine
# once P2 (payment state machines) lands. Release build fails while this tag
# remains in the tree.
@router.post("/risk-check", response_model=RiskCheckResponse)
async def post_risk_check(body: RiskCheckRequest) -> RiskCheckResponse:
    payment_id = str(uuid.uuid4())
    order_id = f"order_stub_{payment_id[:8]}" if body.method == "checkout" else None
    return RiskCheckResponse(decision="ALLOW", payment_id=payment_id, order_id=order_id)

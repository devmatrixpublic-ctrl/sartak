from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from app.core.schemas import StrictInput


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class Decision(StrictInput):
    level: Literal["NONE", "LOG", "NUDGE", "HARD", "TRUSTED_CONTACT"]
    score: float = Field(allow_inf_nan=False)
    reasons: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=3)


class RiskCheckRequest(StrictInput):
    decision: Decision
    method: Literal["upi_intent", "checkout"]
    # Sanity bounds, not product limits: positive, finite, at most Rs 1 crore. NaN used to reach the
    # database as NULL and surface as a 500.
    amount: float = Field(gt=0, le=10_000_000, allow_inf_nan=False)
    payee_hash: str = Field(min_length=1, max_length=128)
    is_p2p: Optional[bool] = None
    # "Continue anyway": release the caller's own held payment (payment_id) instead of creating a new one.
    override: bool = False
    payment_id: Optional[str] = Field(default=None, max_length=36)


class RiskCheckResponse(BaseModel):
    decision: Literal["HOLD", "ALLOW"]
    payment_id: str
    order_id: Optional[str] = None
    hold_reason: Optional[Literal["detector", "payee_fan_in"]] = None

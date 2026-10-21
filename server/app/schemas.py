from typing import Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class Decision(BaseModel):
    level: Literal["NONE", "NUDGE", "HARD", "TRUSTED_CONTACT"]
    score: float
    reasons: list[str] = Field(default_factory=list, max_length=3)


class RiskCheckRequest(BaseModel):
    decision: Decision
    method: Literal["upi_intent", "checkout"]
    amount: float
    payee_hash: str
    is_p2p: Optional[bool] = None


class RiskCheckResponse(BaseModel):
    decision: Literal["HOLD", "ALLOW"]
    payment_id: str
    order_id: Optional[str] = None

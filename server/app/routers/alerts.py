from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.alerts.fcm_client import FcmClient, get_fcm_client
from app.alerts.service import send_alert
from app.auth.dependencies import require_device
from app.core.errors import ApiError
from app.core.schemas import StrictInput
from app.core.settings import Settings, get_settings
from app.db.session import get_db

router = APIRouter(tags=["alerts"])


def fcm_client_dependency(settings: Settings = Depends(get_settings)) -> FcmClient:
    return get_fcm_client(settings.firebase_credentials_json)


class AlertIn(StrictInput):
    device_id: str = Field(min_length=1, max_length=36)
    type: Literal["alarm", "long_session"]
    reasons: Optional[list[Annotated[str, Field(max_length=64)]]] = Field(default=None, max_length=10)
    payment_id: Optional[str] = Field(default=None, max_length=36)


class AlertOut(BaseModel):
    accepted: bool


@router.post("/alert", response_model=AlertOut)
async def post_alert(
    body: AlertIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
    fcm_client: FcmClient = Depends(fcm_client_dependency),
) -> AlertOut:
    if body.device_id != device_id:
        raise ApiError(403, "forbidden", "Cannot raise an alert on behalf of another device")

    send_alert(
        db,
        owner_device_id=device_id,
        alert_type=body.type,
        reasons=body.reasons or [],
        payment_id=body.payment_id,
        fcm_client=fcm_client,
    )
    # Always 2xx once the alert is recorded — a stale token or missing link
    # is a routine, logged outcome, not a request failure.
    return AlertOut(accepted=True)

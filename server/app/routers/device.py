from fastapi import APIRouter, Depends, Response
from pydantic import Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_device
from app.core.schemas import StrictInput
from app.db.models import Account, Alert, Device, Payment, RefreshToken, TrustedInvite, TrustedLink
from app.db.session import get_db

router = APIRouter(tags=["device"])


class PushTokenIn(StrictInput):
    fcm_token: str = Field(min_length=1, max_length=4096)


@router.put("/device/push-token", status_code=204)
async def put_push_token(body: PushTokenIn, device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> Response:
    """A phone tells the server where its own notifications go, so a person who knows only its owner's phone number can reach it."""
    device = db.get(Device, device_id)
    if device is not None:
        device.fcm_token = body.fcm_token
        db.commit()
    return Response(status_code=204)


@router.delete("/device", status_code=204)
async def delete_device(device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> Response:
    """"Delete my data": erase everything the server holds for the calling device.

    Payments, alerts, trusted links (as owner or as contact), refresh tokens and the device record itself. Pattern
    signatures carry no device id by design, so there is nothing of this device's in them to remove. Webhook event ids
    are Razorpay's, not the device's, and stay for deduplication.
    """
    db.execute(delete(Payment).where(Payment.device_id == device_id))
    db.execute(delete(Alert).where(Alert.device_id == device_id))
    db.execute(delete(TrustedLink).where(or_(TrustedLink.owner_device_id == device_id, TrustedLink.trusted_device_id == device_id)))
    db.execute(delete(RefreshToken).where(RefreshToken.device_id == device_id))
    db.execute(delete(TrustedInvite).where(TrustedInvite.contact_device_id == device_id))
    account_id = db.scalar(select(Device.account_id).where(Device.id == device_id))
    db.execute(delete(Device).where(Device.id == device_id))
    if account_id and not db.scalar(select(Device.id).where(Device.account_id == account_id).limit(1)):
        db.execute(delete(Account).where(Account.id == account_id))  # the last phone of an account is gone, so is the account
    db.commit()
    return Response(status_code=204)

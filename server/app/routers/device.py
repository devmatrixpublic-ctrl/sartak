from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import require_device
from app.db.models import Alert, Device, Payment, RefreshToken, TrustedLink
from app.db.session import get_db

router = APIRouter(tags=["device"])


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
    db.execute(delete(Device).where(Device.id == device_id))
    db.commit()
    return Response(status_code=204)

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_device
from app.core.errors import ApiError
from app.core.schemas import StrictInput
from app.db.models import Device, TrustedLink
from app.db.session import get_db

router = APIRouter(tags=["trusted-contact"])


class TrustedContactIn(StrictInput):
    trusted_device_id: str
    fcm_token: str


class TrustedContactOut(BaseModel):
    linked: bool


@router.post("/trusted-contact", response_model=TrustedContactOut)
async def post_trusted_contact(
    body: TrustedContactIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
) -> TrustedContactOut:
    # The trusted contact must already have registered via /auth/device; we never fabricate a device.
    trusted_device = db.get(Device, body.trusted_device_id)
    if trusted_device is None or trusted_device.revoked:
        raise ApiError(404, "trusted_device_not_found", "The trusted contact's device is not registered.")
    trusted_device.fcm_token = body.fcm_token
    db.add(trusted_device)

    existing = (
        db.query(TrustedLink)
        .filter(
            TrustedLink.owner_device_id == device_id,
            TrustedLink.trusted_device_id == body.trusted_device_id,
        )
        .one_or_none()
    )
    if existing is None:
        db.add(TrustedLink(owner_device_id=device_id, trusted_device_id=body.trusted_device_id))

    db.commit()
    return TrustedContactOut(linked=True)

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import ensure_device_exists, require_device
from app.core.schemas import StrictInput
from app.db.models import TrustedLink
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
    ensure_device_exists(db, device_id)
    trusted_device = ensure_device_exists(db, body.trusted_device_id)
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

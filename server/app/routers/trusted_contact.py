import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.alerts.fcm_client import FcmClient, FcmTokenInvalid
from app.auth.dependencies import require_device
from app.core.errors import ApiError
from app.core.schemas import StrictInput
from app.db.models import Device, TrustedLink
from app.db.session import get_db
from app.routers.alerts import fcm_client_dependency

router = APIRouter(tags=["trusted-contact"])
logger = logging.getLogger("satark.trusted_contact")

# One short line, no names, numbers or payment details.
REQUEST_PUSH_TITLE = "Satark"
REQUEST_PUSH_BODY = "Someone asked you to be their trusted contact."


class TrustedContactIn(StrictInput):
    trusted_device_id: str = Field(min_length=1, max_length=36)
    fcm_token: str = Field(min_length=1, max_length=4096)


class TrustedContactOut(BaseModel):
    linked: bool
    status: Literal["pending", "accepted", "revoked"]


class TrustedRequestOut(BaseModel):
    owner_device_id: str


class TrustedRequestsOut(BaseModel):
    requests: list[TrustedRequestOut]


class RespondIn(StrictInput):
    owner_device_id: str = Field(min_length=1, max_length=36)
    decision: Literal["accept", "decline"]


@router.post("/trusted-contact", response_model=TrustedContactOut)
async def post_trusted_contact(
    body: TrustedContactIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
    fcm_client: FcmClient = Depends(fcm_client_dependency),
) -> TrustedContactOut:
    """Ask a device to be this device's trusted contact. The link starts pending: nothing is sent to the contact until they accept."""
    # The trusted contact must already have registered via /auth/device; we never fabricate a device.
    trusted_device = db.get(Device, body.trusted_device_id)
    if trusted_device is None or trusted_device.revoked:
        raise ApiError(404, "trusted_device_not_found", "The trusted contact's device is not registered.")
    if body.trusted_device_id == device_id:
        raise ApiError(422, "invalid_contact", "You cannot be your own trusted contact.")
    trusted_device.fcm_token = body.fcm_token
    db.add(trusted_device)

    link = (
        db.query(TrustedLink)
        .filter(TrustedLink.owner_device_id == device_id, TrustedLink.trusted_device_id == body.trusted_device_id)
        .one_or_none()
    )
    ask = False
    if link is None:
        link = TrustedLink(owner_device_id=device_id, trusted_device_id=body.trusted_device_id, status="pending")
        db.add(link)
        ask = True
    elif link.status == "revoked":
        link.status = "pending"
        ask = True
    db.commit()

    if ask:
        try:
            fcm_client.send(
                body.fcm_token, title=REQUEST_PUSH_TITLE, body=REQUEST_PUSH_BODY,
                data={"type": "link_request", "owner_device_id": device_id},
            )
        except FcmTokenInvalid:
            logger.warning("link_request_stale_fcm_token", extra={"trusted_device_id": body.trusted_device_id})
    return TrustedContactOut(linked=True, status=link.status)


@router.get("/trusted-contact/requests", response_model=TrustedRequestsOut)
async def get_trusted_requests(device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> TrustedRequestsOut:
    """Pending requests addressed to the calling device (it is the one being asked)."""
    rows = db.query(TrustedLink).filter(TrustedLink.trusted_device_id == device_id, TrustedLink.status == "pending").all()
    return TrustedRequestsOut(requests=[TrustedRequestOut(owner_device_id=r.owner_device_id) for r in rows])


@router.post("/trusted-contact/respond", response_model=TrustedContactOut)
async def post_trusted_respond(
    body: RespondIn, device_id: str = Depends(require_device), db: Session = Depends(get_db),
) -> TrustedContactOut:
    """The contact's answer. Only the asked device can answer; accepting needs a pending request; declining also ends an accepted link."""
    link = (
        db.query(TrustedLink)
        .filter(TrustedLink.owner_device_id == body.owner_device_id, TrustedLink.trusted_device_id == device_id)
        .one_or_none()
    )
    if link is None or link.status == "revoked":
        raise ApiError(404, "not_found", "No such request.")
    if body.decision == "accept":
        if link.status != "pending":
            raise ApiError(409, "invalid_state", "This request was already answered.")
        link.status = "accepted"
    else:
        link.status = "revoked"
    db.commit()
    return TrustedContactOut(linked=link.status == "accepted", status=link.status)


@router.delete("/trusted-contact/{trusted_device_id}", response_model=TrustedContactOut)
async def delete_trusted_contact(
    trusted_device_id: str, device_id: str = Depends(require_device), db: Session = Depends(get_db),
) -> TrustedContactOut:
    """The owner removes a trusted contact: the link is revoked and receives nothing more."""
    link = (
        db.query(TrustedLink)
        .filter(TrustedLink.owner_device_id == device_id, TrustedLink.trusted_device_id == trusted_device_id)
        .one_or_none()
    )
    if link is None:
        raise ApiError(404, "not_found", "No such trusted contact.")
    link.status = "revoked"
    db.commit()
    return TrustedContactOut(linked=False, status="revoked")

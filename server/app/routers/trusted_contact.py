import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts.identity import E164, display_name, phone_hash
from app.alerts.fcm_client import FcmClient, FcmTokenInvalid
from app.auth.dependencies import require_device
from app.auth.ratelimit import get_rate_limiter
from app.core.errors import ApiError
from app.core.schemas import StrictInput
from app.core.settings import Settings, get_settings
from app.db.models import Account, Device, TrustedLink
from app.db.session import get_db
from app.routers.alerts import fcm_client_dependency

router = APIRouter(tags=["trusted-contact"])
logger = logging.getLogger("satark.trusted_contact")

# One short line, no names, numbers or payment details.
REQUEST_PUSH_TITLE = "Satark"
REQUEST_PUSH_BODY = "Someone asked you to be their trusted contact."
NAMED_REQUEST_PUSH_BODY = "{name} asked you to be their trusted contact."
# Looking a number up must not become a way to ask "who uses Satark?": a limited number of tries, and the same answer either way.
PHONE_LOOKUPS_PER_HOUR = 10


class TrustedContactIn(StrictInput):
    trusted_device_id: str = Field(min_length=1, max_length=36)
    fcm_token: str = Field(min_length=1, max_length=4096)


class TrustedContactOut(BaseModel):
    linked: bool
    status: Literal["pending", "accepted", "revoked"]


class TrustedRequestOut(BaseModel):
    owner_device_id: str
    owner_name: Optional[str] = None


class MyContactOut(BaseModel):
    trusted_device_id: str
    name: Optional[str] = None


class MyContactsOut(BaseModel):
    contacts: list[MyContactOut]


class ByPhoneIn(StrictInput):
    phone: str = Field(pattern=E164.pattern)


class ByPhoneOut(BaseModel):
    # Always true when the request was well formed, whether or not that number has Satark.
    requested: bool


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
            _send_request_push(db, device_id, body.fcm_token, fcm_client)
        except FcmTokenInvalid:
            logger.warning("link_request_stale_fcm_token", extra={"trusted_device_id": body.trusted_device_id})
    return TrustedContactOut(linked=True, status=link.status)


def _send_request_push(db: Session, owner_device_id: str, token: str, fcm_client: FcmClient) -> None:
    name = display_name(db, owner_device_id)
    fcm_client.send(
        token, title=REQUEST_PUSH_TITLE, body=NAMED_REQUEST_PUSH_BODY.format(name=name) if name else REQUEST_PUSH_BODY,
        data={"type": "link_request", "owner_device_id": owner_device_id, **({"owner_name": name} if name else {})},
    )


@router.get("/trusted-contact", response_model=MyContactsOut, response_model_exclude_none=True)
async def get_my_trusted_contacts(device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> MyContactsOut:
    """Who has said yes to being this device's trusted contact, by the name they signed in with. Pending requests are not listed:
    showing them would tell a person who tried a phone number whether that number has Satark."""
    rows = db.query(TrustedLink).filter(TrustedLink.owner_device_id == device_id, TrustedLink.status == "accepted").order_by(TrustedLink.created_at).all()
    return MyContactsOut(contacts=[MyContactOut(trusted_device_id=r.trusted_device_id, name=display_name(db, r.trusted_device_id)) for r in rows])


@router.post("/trusted-contact/by-phone", response_model=ByPhoneOut)
async def post_trusted_contact_by_phone(
    body: ByPhoneIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
    fcm_client: FcmClient = Depends(fcm_client_dependency),
    settings: Settings = Depends(get_settings),
) -> ByPhoneOut:
    """Ask the person with this phone number to be this device's trusted contact. The number is hashed and forgotten; the request goes
    to the newest phone that person signed in on, using the push address that phone registered itself. The answer never says whether
    the number has Satark."""
    allowed, _retry_after = get_rate_limiter(settings).hit(f"rl:phonelink:{device_id}", PHONE_LOOKUPS_PER_HOUR, 3600)
    if not allowed:
        raise ApiError(429, "rate_limited", "Too many tries. Wait a while and try again.")

    account = db.query(Account).filter(Account.phone_hash == phone_hash(body.phone, settings)).one_or_none()
    contact = None
    if account is not None:
        contact = (
            db.query(Device)
            .filter(Device.account_id == account.id, Device.revoked.is_(False), Device.fcm_token.is_not(None), Device.id != device_id)
            .order_by(Device.created_at.desc())
            .first()
        )
    if contact is None:
        return ByPhoneOut(requested=True)

    link = (
        db.query(TrustedLink)
        .filter(TrustedLink.owner_device_id == device_id, TrustedLink.trusted_device_id == contact.id)
        .one_or_none()
    )
    ask = False
    if link is None:
        db.add(TrustedLink(owner_device_id=device_id, trusted_device_id=contact.id, status="pending"))
        ask = True
    elif link.status == "revoked":
        link.status = "pending"
        ask = True
    db.commit()
    if ask:
        try:
            _send_request_push(db, device_id, contact.fcm_token, fcm_client)
        except FcmTokenInvalid:
            logger.warning("link_request_stale_fcm_token", extra={"trusted_device_id": contact.id})
    return ByPhoneOut(requested=True)


@router.get("/trusted-contact/requests", response_model=TrustedRequestsOut, response_model_exclude_none=True)
async def get_trusted_requests(device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> TrustedRequestsOut:
    """Pending requests addressed to the calling device (it is the one being asked)."""
    rows = db.query(TrustedLink).filter(TrustedLink.trusted_device_id == device_id, TrustedLink.status == "pending").all()
    return TrustedRequestsOut(requests=[TrustedRequestOut(owner_device_id=r.owner_device_id, owner_name=display_name(db, r.owner_device_id)) for r in rows])


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

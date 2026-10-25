import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts.identity import display_name
from app.alerts.fcm_client import FcmClient, FcmTokenInvalid
from app.auth.dependencies import require_device
from app.auth.ratelimit import get_rate_limiter
from app.core.errors import ApiError
from app.core.schemas import StrictInput
from app.core.settings import Settings, get_settings
from app.db.models import Device, TrustedInvite, TrustedLink
from app.db.session import get_db
from app.routers.alerts import fcm_client_dependency

router = APIRouter(tags=["trusted-contact"])
logger = logging.getLogger("satark.trusted_contact")

# One short line, no names, numbers or payment details.
REQUEST_PUSH_TITLE = "Satark"
REQUEST_PUSH_BODY = "Someone asked you to be their trusted contact."
NAMED_REQUEST_PUSH_BODY = "{name} asked you to be their trusted contact."
# An invite code is guessable only by trying: a short life, one use, and a limit on tries per phone.
INVITE_TTL_SECONDS = 600
INVITE_TRIES_PER_HOUR = 10
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: easy to read out loud
CODE_LENGTH = 8


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


class InviteIn(StrictInput):
    # The contact's own push address, sent by the contact's own phone (never by the person asking).
    fcm_token: str = Field(min_length=1, max_length=4096)


class InviteOut(BaseModel):
    code: str
    expires_in: int


class JoinIn(StrictInput):
    code: str = Field(min_length=4, max_length=24)


class JoinOut(BaseModel):
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


def _normalize(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", code.upper())


def _code_hash(code: str, settings: Settings) -> str:
    pepper = (settings.phone_pepper or settings.jwt_secret).encode()
    return hmac.new(pepper, b"invite:" + code.encode(), hashlib.sha256).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _limit(settings: Settings, key: str) -> None:
    allowed, _ = get_rate_limiter(settings).hit(key, INVITE_TRIES_PER_HOUR, 3600)
    if not allowed:
        raise ApiError(429, "rate_limited", "Too many tries. Wait a while and try again.")


@router.post("/trusted-contact/invite", response_model=InviteOut)
async def post_invite(
    body: InviteIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InviteOut:
    """The would-be contact asks for a short code to give the person they will protect. The code lives ten minutes and works once;
    asking again cancels the earlier one. The contact's push address is stored from this call, so it is always their own."""
    _limit(settings, f"rl:invite:{device_id}")
    device = db.get(Device, device_id)
    if device is None:
        raise ApiError(404, "device_not_found", "This phone is not registered.")
    device.fcm_token = body.fcm_token
    db.query(TrustedInvite).filter(TrustedInvite.contact_device_id == device_id, TrustedInvite.used.is_(False)).update({"used": True})
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    db.add(TrustedInvite(
        contact_device_id=device_id, code_hash=_code_hash(code, settings),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=INVITE_TTL_SECONDS),
    ))
    db.commit()
    return InviteOut(code=f"{code[:4]}-{code[4:]}", expires_in=INVITE_TTL_SECONDS)


@router.post("/trusted-contact/join", response_model=JoinOut)
async def post_join(
    body: JoinIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
    fcm_client: FcmClient = Depends(fcm_client_dependency),
    settings: Settings = Depends(get_settings),
) -> JoinOut:
    """The person being protected types the code the contact showed. The contact is asked to accept; nothing reaches them until they do.
    A wrong, used or expired code all get the same answer."""
    _limit(settings, f"rl:join:{device_id}")
    invite = db.query(TrustedInvite).filter(
        TrustedInvite.code_hash == _code_hash(_normalize(body.code), settings), TrustedInvite.used.is_(False)
    ).one_or_none()
    contact = db.get(Device, invite.contact_device_id) if invite is not None else None
    if invite is None or _aware(invite.expires_at) <= datetime.now(timezone.utc) or contact is None or contact.revoked or not contact.fcm_token:
        raise ApiError(404, "invalid_code", "That code is not valid or has expired. Ask them for a new one.")
    if contact.id == device_id:
        raise ApiError(422, "invalid_contact", "You cannot be your own trusted contact.")
    invite.used = True

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
    return JoinOut(requested=True)


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

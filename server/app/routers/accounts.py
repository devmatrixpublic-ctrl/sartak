from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts.identity import PhoneVerifier, phone_hash, phone_verifier_dependency
from app.auth.dependencies import require_device
from app.core.errors import ApiError
from app.core.schemas import StrictInput
from app.core.settings import Settings, get_settings
from app.db.models import Account, Device
from app.db.session import get_db

router = APIRouter(tags=["account"])


class AccountIn(StrictInput):
    id_token: str = Field(min_length=1, max_length=8192)
    name: Optional[str] = Field(default=None, max_length=60)


class NameIn(StrictInput):
    name: str = Field(min_length=1, max_length=60)


class AccountOut(BaseModel):
    name: Optional[str] = None
    created: bool = False


def _clean(name: Optional[str]) -> Optional[str]:
    name = (name or "").strip()
    return name or None


def _account_of(db: Session, device_id: str) -> Optional[Account]:
    device = db.get(Device, device_id)
    return db.get(Account, device.account_id) if device is not None and device.account_id else None


@router.post("/account", response_model=AccountOut)
async def post_account(
    body: AccountIn,
    device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
    verifier: PhoneVerifier = Depends(phone_verifier_dependency),
    settings: Settings = Depends(get_settings),
) -> AccountOut:
    """Sign in or sign up this phone. The sign-in token proves a phone number; the account is found (or made) by its keyed hash.
    Signing in on a second phone with the same number joins the same account."""
    phone = verifier.verify(body.id_token)
    h = phone_hash(phone, settings)
    account = db.query(Account).filter(Account.phone_hash == h).one_or_none()
    created = account is None
    if created:
        account = Account(phone_hash=h, name=_clean(body.name))
        db.add(account)
        db.flush()
    elif _clean(body.name):
        account.name = _clean(body.name)
    device = db.get(Device, device_id)
    if device is None:
        raise ApiError(404, "device_not_found", "This phone is not registered.")
    device.account_id = account.id
    db.commit()
    return AccountOut(name=account.name, created=created)


@router.get("/account", response_model=AccountOut)
async def get_account(device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> AccountOut:
    account = _account_of(db, device_id)
    if account is None:
        raise ApiError(404, "no_account", "This phone has no account.")
    return AccountOut(name=account.name)


@router.delete("/account", status_code=204)
async def delete_account_link(device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> Response:
    """Sign out: this phone stops belonging to the account. The account stays for its other phones; "Delete my data" removes the rest."""
    device = db.get(Device, device_id)
    if device is not None and device.account_id:
        account_id = device.account_id
        device.account_id = None
        db.flush()
        if not db.query(Device.id).filter(Device.account_id == account_id).first():
            db.query(Account).filter(Account.id == account_id).delete()
        db.commit()
    return Response(status_code=204)


@router.patch("/account", response_model=AccountOut)
async def patch_account(body: NameIn, device_id: str = Depends(require_device), db: Session = Depends(get_db)) -> AccountOut:
    account = _account_of(db, device_id)
    if account is None:
        raise ApiError(404, "no_account", "This phone has no account.")
    account.name = _clean(body.name)
    db.commit()
    return AccountOut(name=account.name)

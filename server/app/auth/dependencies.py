from fastapi import Header
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Device


# SATARK_STUB: dev-token stand-in for M4's /auth/device + require_device(role).
# The bearer token is treated as the device_id directly. Replaced once
# /auth/device (Key Attestation) is live; release build fails while this
# tag remains.
async def require_device(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "unauthorized", "Missing bearer token")
    device_id = authorization.removeprefix("Bearer ").strip()
    if not device_id:
        raise ApiError(401, "unauthorized", "Empty bearer token")
    return device_id


# SATARK_STUB: dev-only convenience so FK-backed rows (payments, alerts) can
# be created against a device_id minted by the dev-token stub above, without
# a real Key Attestation round trip. Removed with the stub dependency.
def ensure_device_exists(db: Session, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        device = Device(
            id=device_id,
            public_key=f"dev-stub:{device_id}",
            attestation_level="software",
            verified_boot_state="unverified",
            role="device",
        )
        db.add(device)
        db.commit()
        db.refresh(device)
    return device

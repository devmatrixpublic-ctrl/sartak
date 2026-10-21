"""Storage the auth logic needs, behind a Protocol, with a SQL implementation on M3's tables.

Atomicity lives in single UPDATE statements (challenge consume, refresh take) so two
concurrent requests cannot both succeed, on SQLite and Postgres alike.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import AuthChallenge, Device, RefreshToken


@dataclass
class DeviceRecord:
    device_id: str
    public_key: str                     # base64 SPKI
    attestation_level: str              # "software" | "TEE" | "StrongBox"
    verified_boot_state: str            # "verified" | "self_signed" | "unverified" | "failed" | "unknown"
    role: str = "device"
    revoked: bool = False


@dataclass
class RefreshRecord:
    device_id: str
    expires_at: float
    used: bool = False


class AuthStore(Protocol):
    def put_challenge(self, challenge: str, expires_at: float) -> None: ...
    def consume_challenge(self, challenge: str, now: float) -> bool: ...
    def upsert_device(self, record: DeviceRecord) -> DeviceRecord: ...
    def get_device(self, device_id: str) -> DeviceRecord | None: ...
    def revoke_device(self, device_id: str) -> None: ...
    def put_refresh(self, token_hash: str, record: RefreshRecord) -> None: ...
    def take_refresh(self, token_hash: str) -> RefreshRecord | None: ...


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


def _ts(value: datetime) -> float:
    if value.tzinfo is None:            # SQLite returns naive datetimes; we only ever store UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _record(row: Device) -> DeviceRecord:
    return DeviceRecord(row.id, row.public_key, row.attestation_level, row.verified_boot_state,
                        row.role, bool(row.revoked))


class SqlAuthStore:
    def __init__(self, db: Session):
        self.db = db

    def put_challenge(self, challenge: str, expires_at: float) -> None:
        self.db.add(AuthChallenge(nonce=challenge, expires_at=_dt(expires_at)))
        self.db.commit()

    def consume_challenge(self, challenge: str, now: float) -> bool:
        result = self.db.execute(
            sa.update(AuthChallenge)
            .where(AuthChallenge.nonce == challenge,
                   AuthChallenge.used == sa.false(),
                   AuthChallenge.expires_at >= _dt(now))
            .values(used=True)
        )
        self.db.commit()
        return result.rowcount == 1

    def upsert_device(self, record: DeviceRecord) -> DeviceRecord:
        row = self.db.get(Device, record.device_id)
        if row is None:
            row = Device(id=record.device_id, role=record.role)
            self.db.add(row)
        # An existing row keeps its role; only hardware re-attestation may clear `revoked`.
        row.public_key = record.public_key
        row.attestation_level = record.attestation_level
        row.verified_boot_state = record.verified_boot_state
        row.revoked = False
        self.db.commit()
        self.db.refresh(row)
        return _record(row)

    def get_device(self, device_id: str) -> DeviceRecord | None:
        row = self.db.get(Device, device_id)
        return _record(row) if row is not None else None

    def revoke_device(self, device_id: str) -> None:
        self.db.execute(sa.update(Device).where(Device.id == device_id).values(revoked=True))
        self.db.commit()

    def put_refresh(self, token_hash: str, record: RefreshRecord) -> None:
        self.db.add(RefreshToken(token_hash=token_hash, device_id=record.device_id,
                                 expires_at=_dt(record.expires_at)))
        self.db.commit()

    def take_refresh(self, token_hash: str) -> RefreshRecord | None:
        row = self.db.get(RefreshToken, token_hash)
        if row is None:
            return None
        device_id, expires_at, was_used = row.device_id, _ts(row.expires_at), bool(row.used)
        result = self.db.execute(
            sa.update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.used == sa.false())
            .values(used=True)
        )
        self.db.commit()
        # Lost a race with a concurrent use of the same token: that is a replay too.
        return RefreshRecord(device_id, expires_at, used=was_used or result.rowcount == 0)

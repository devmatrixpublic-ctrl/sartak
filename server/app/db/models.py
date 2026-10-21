import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    public_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    attestation_level: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_boot_state: Mapped[str] = mapped_column(String(32), nullable=False)
    fcm_token: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="device")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    payments: Mapped[list["Payment"]] = relationship(back_populates="device")


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nonce: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TrustedLink(Base):
    __tablename__ = "trusted_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    trusted_device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("owner_device_id", "trusted_device_id", name="uq_trusted_link_pair"),)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payee_hash: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    razorpay_order_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    reported_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reported_txn_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    handed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped["Device"] = relationship(back_populates="payments")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Signature(Base):
    """Pattern signatures only. No phone numbers, names, or raw amounts linked to a device."""

    __tablename__ = "signatures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pattern_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    features_json: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

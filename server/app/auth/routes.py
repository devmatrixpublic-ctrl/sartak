"""POST /auth/challenge, /auth/device, /auth/refresh (+ the dev-token stub). Shapes follow contracts/api.yaml."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.clientip import client_ip
from app.core.schemas import StrictInput

from .dependencies import get_auth_service
from .errors import AuthError
from .service import CHALLENGE_LIMIT, REGISTER_LIMIT, ROLES, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class ChallengeOut(BaseModel):
    challenge: str
    expires_at: datetime


class DeviceIn(StrictInput):
    challenge: str = Field(min_length=20, max_length=128)
    public_key: str = Field(min_length=1, max_length=4096)
    attestation_chain: list[str] = Field(min_length=2, max_length=6)
    role: Literal["device"] = "device"        # contract field; admin can never be requested


class RefreshIn(StrictInput):
    refresh_token: str = Field(min_length=20, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    device_id: str


def _ip(request: Request, svc: AuthService) -> str:
    # The immediate peer unless SATARK_TRUSTED_PROXY_HOPS says how many proxies append to X-Forwarded-For (app/core/clientip.py).
    return client_ip(request, svc.settings.trusted_proxy_hops)


@router.post("/challenge", response_model=ChallengeOut)
def challenge(request: Request, svc: AuthService = Depends(get_auth_service)) -> ChallengeOut:
    svc.limit(f"rl:challenge:{_ip(request, svc)}", CHALLENGE_LIMIT)
    value, expires_at = svc.issue_challenge()
    return ChallengeOut(challenge=value, expires_at=datetime.fromtimestamp(expires_at, timezone.utc))


@router.post("/device", response_model=TokenOut)
def device(body: DeviceIn, request: Request, svc: AuthService = Depends(get_auth_service)) -> TokenOut:
    svc.limit(f"rl:register:{_ip(request, svc)}", REGISTER_LIMIT)
    record, tokens = svc.register_device(body.challenge, body.public_key, body.attestation_chain)
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                    expires_in=tokens.expires_in, device_id=record.device_id)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, request: Request, svc: AuthService = Depends(get_auth_service)) -> TokenOut:
    svc.limit(f"rl:register:{_ip(request, svc)}", REGISTER_LIMIT)
    record, tokens = svc.refresh(body.refresh_token)
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                    expires_in=tokens.expires_in, device_id=record.device_id)


class DevTokenIn(StrictInput):                                  # support for the dev-token stub below
    device_id: str = Field(min_length=1, max_length=36)
    role: str = "device"


@router.post("/dev-token", response_model=TokenOut, include_in_schema=False)  # SATARK_STUB
def dev_token(body: DevTokenIn, svc: AuthService = Depends(get_auth_service)) -> TokenOut:
    """Answers 404 unless SATARK_ENV=dev and SATARK_AUTH_ENABLE_DEV_TOKEN=1 (checked in the service)."""
    if not (svc.settings.is_dev and svc.settings.auth_enable_dev_token):
        raise AuthError(404, "not_found", "Not found.")
    if body.role not in ROLES:
        raise AuthError(422, "invalid_request", "Unknown role.")
    tokens = svc.dev_token(body.device_id, body.role)
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                    expires_in=tokens.expires_in, device_id=body.device_id)

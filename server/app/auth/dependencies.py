"""FastAPI dependencies. `require_device` keeps the shape M3's routers already use:
`device_id: str = Depends(require_device)`."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db

from .attestation import AttestationPolicy, load_roots_pem
from .config import expected_signing_digests
from .errors import AuthError, unauthorized
from .ratelimit import get_rate_limiter
from .revocation import GoogleRevocationList
from .service import AuthService, DeviceIdentity
from .store import SqlAuthStore

_policy: AttestationPolicy | None = None
_revocation: GoogleRevocationList | None = None


def reset_auth_caches() -> None:
    global _policy, _revocation
    _policy = _revocation = None


def get_attestation_policy(settings: Settings) -> AttestationPolicy | None:
    """Built once from the pinned roots file; None (-> 503 on /auth/device) if not configured."""
    global _policy, _revocation
    if _policy is None and settings.auth_attestation_roots:
        _revocation = _revocation or GoogleRevocationList()
        _policy = AttestationPolicy(
            roots=load_roots_pem(Path(settings.auth_attestation_roots).read_bytes()),
            expected_package=settings.auth_expected_package,
            expected_signing_sha256=expected_signing_digests(settings),
            revoked=_revocation,
            require_hardware=settings.auth_require_hardware or not settings.is_dev,
            clock=lambda: datetime.now(timezone.utc),
        )
    return _policy


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    settings = get_settings()
    return AuthService(settings, SqlAuthStore(db), get_rate_limiter(settings), get_attestation_policy(settings))


def _authenticate(authorization: str | None, svc: AuthService, role: str) -> DeviceIdentity:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise unauthorized("missing_token", "Authentication required.")
    identity = svc.authenticate(token.strip())
    if identity.role != role:
        raise AuthError(403, "forbidden_role", "This account may not use this endpoint.")
    svc.limit_device(identity.device_id)
    return identity


def require_device(
    authorization: str | None = Header(default=None),
    svc: AuthService = Depends(get_auth_service),
) -> str:
    """401 without a valid token, 403 for a non-device role, 429 over the per-device limit."""
    return _authenticate(authorization, svc, "device").device_id


def require_role(role: str):
    def dependency(
        authorization: str | None = Header(default=None),
        svc: AuthService = Depends(get_auth_service),
    ) -> DeviceIdentity:
        return _authenticate(authorization, svc, role)

    return dependency


def ensure_owner(identity: DeviceIdentity, owner_device_id: str) -> None:
    """Object-level access check. Another device's object looks exactly like a missing one."""
    if identity.role != "admin" and identity.device_id != owner_device_id:
        raise AuthError(404, "not_found", "Not found.")

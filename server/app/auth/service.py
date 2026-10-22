"""Auth logic: challenges, device registration, tokens, refresh rotation."""
from __future__ import annotations

import base64
import binascii
import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Callable

import jwt

from app.core.settings import Settings

from .attestation import AttestationError, AttestationPolicy, BootState, SecurityLevel, verify_attestation
from .errors import AuthError, unauthorized
from .ratelimit import RateLimiter
from .store import AuthStore, DeviceRecord, RefreshRecord

ROLES = ("device", "admin")
CHALLENGE_LIMIT = (10, 60)          # hits, window seconds (per client IP)
REGISTER_LIMIT = (10, 60)
_B64_LIMIT = 16 * 1024
_LEVEL_NAMES = {SecurityLevel.SOFTWARE: "software", SecurityLevel.TRUSTED_ENVIRONMENT: "TEE",
                SecurityLevel.STRONGBOX: "StrongBox"}
_BOOT_NAMES = {BootState.VERIFIED: "verified", BootState.SELF_SIGNED: "self_signed",
               BootState.UNVERIFIED: "unverified", BootState.FAILED: "failed"}


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    role: str


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(value: str, what: str) -> bytes:
    if len(value) > _B64_LIMIT:
        raise AuthError(400, "invalid_request", f"{what} is too large.")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise AuthError(400, "invalid_request", f"{what} is not valid base64.")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def device_id_for(spki_der: bytes) -> str:
    """Deterministic UUID from the public key, so re-registering the same key keeps one identity."""
    return str(uuid.UUID(bytes=hashlib.sha256(spki_der).digest()[:16], version=5))


class AuthService:
    def __init__(
        self,
        settings: Settings,
        store: AuthStore,
        limiter: RateLimiter,
        policy: AttestationPolicy | None,
        clock: Callable[[], float] = time.time,
    ):
        self.settings = settings
        self.store = store
        self.limiter = limiter
        self.policy = policy
        self.clock = clock

    # rate limiting -------------------------------------------------------------------
    def limit(self, key: str, rule: tuple[int, int]) -> None:
        allowed, retry_after = self.limiter.hit(key, rule[0], rule[1])
        if not allowed:
            raise AuthError(429, "rate_limited", "Too many requests; slow down.",
                            {"Retry-After": str(retry_after)})

    def limit_device(self, device_id: str) -> None:
        self.limit(f"rl:device:{device_id}", (self.settings.rate_limit_per_minute, 60))

    # challenge -----------------------------------------------------------------------
    def issue_challenge(self) -> tuple[str, float]:
        challenge = b64url(secrets.token_bytes(32))
        expires_at = self.clock() + self.settings.auth_challenge_ttl_seconds
        self.store.put_challenge(challenge, expires_at)
        return challenge, expires_at

    # registration --------------------------------------------------------------------
    def register_device(self, challenge: str, public_key_b64: str, chain_b64: list[str]
                        ) -> tuple[DeviceRecord, TokenPair]:
        if self.policy is None:
            raise AuthError(503, "attestation_unavailable", "Attestation is not configured on this server.")
        spki = _b64decode(public_key_b64, "public_key")
        chain = [_b64decode(c, "attestation_chain entry") for c in chain_b64]
        try:
            expected = base64.urlsafe_b64decode(challenge + "=" * (-len(challenge) % 4))
        except (binascii.Error, ValueError):
            raise AuthError(400, "challenge_invalid", "Challenge is invalid, used, or expired.")
        # Consumed first: a failed attempt burns the challenge, so it cannot be probed repeatedly.
        if not self.store.consume_challenge(challenge, self.clock()):
            raise AuthError(400, "challenge_invalid", "Challenge is invalid, used, or expired.")
        try:
            result = verify_attestation(chain, spki, expected, self.policy)
        except AttestationError as exc:
            raise AuthError(400, exc.code, exc.message)
        boot = _BOOT_NAMES.get(result.verified_boot_state, "unknown") if result.verified_boot_state is not None else "unknown"
        record = self.store.upsert_device(DeviceRecord(
            device_id=device_id_for(result.spki_der),
            public_key=base64.b64encode(result.spki_der).decode(),
            attestation_level=_LEVEL_NAMES[result.security_level],
            verified_boot_state=boot,
        ))
        return record, self._issue_pair(record)

    # tokens --------------------------------------------------------------------------
    def _issue_pair(self, record: DeviceRecord) -> TokenPair:
        now = int(self.clock())
        ttl = self.settings.jwt_access_ttl_seconds
        claims = {"sub": record.device_id, "role": record.role, "iat": now, "exp": now + ttl,
                  "jti": uuid.uuid4().hex, "typ": "access"}
        access = jwt.encode(claims, self.settings.jwt_secret, algorithm="HS256")
        refresh = b64url(secrets.token_bytes(32))
        self.store.put_refresh(_hash_token(refresh),
                               RefreshRecord(record.device_id, self.clock() + self.settings.jwt_refresh_ttl_seconds))
        return TokenPair(access, refresh, ttl)

    def refresh(self, refresh_token: str) -> tuple[DeviceRecord, TokenPair]:
        rec = self.store.take_refresh(_hash_token(refresh_token))
        if rec is None or self.clock() > rec.expires_at:
            raise unauthorized("invalid_refresh", "Refresh token is invalid or expired.")
        if rec.used:
            self.store.revoke_device(rec.device_id)
            raise unauthorized("refresh_reuse", "Refresh token was already used; re-register this device.")
        device = self.store.get_device(rec.device_id)
        if device is None or device.revoked:
            raise unauthorized("invalid_refresh", "Device is not active; re-register.")
        return device, self._issue_pair(device)

    def authenticate(self, token: str) -> DeviceIdentity:
        try:
            # Time is checked below against self.clock, the single time source, not PyJWT's wall clock.
            claims = jwt.decode(token, self.settings.jwt_secret, algorithms=["HS256"],
                                options={"require": ["sub", "role", "exp", "typ"],
                                         "verify_exp": False, "verify_iat": False, "verify_nbf": False})
        except jwt.PyJWTError:
            raise unauthorized("invalid_token", "Access token is invalid.")
        if (claims.get("typ") != "access" or claims["role"] not in ROLES
                or not isinstance(claims["exp"], (int, float)) or isinstance(claims["exp"], bool)):
            raise unauthorized("invalid_token", "Access token is invalid.")
        if self.clock() >= claims["exp"]:
            raise unauthorized("token_expired", "Access token expired.")
        device = self.store.get_device(claims["sub"])
        if device is None or device.revoked:
            raise unauthorized("invalid_token", "Device is not active.")
        return DeviceIdentity(device.device_id, device.role)

    # dev stub ------------------------------------------------------------------------
    def dev_token(self, device_id: str, role: str) -> TokenPair:  # SATARK_STUB
        if not (self.settings.is_dev and self.settings.auth_enable_dev_token):
            raise AuthError(404, "not_found", "Not found.")
        record = self.store.get_device(device_id) or self.store.upsert_device(DeviceRecord(
            device_id=device_id, public_key=f"dev-stub:{device_id}", attestation_level="software",
            verified_boot_state="unverified", role=role))
        return self._issue_pair(record)

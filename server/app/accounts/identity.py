"""Who owns this phone number? Turns a sign-in token into a verified phone number, and a phone number into a keyed hash.

The server never stores the number itself. Lookups (later: "link a trusted contact by phone number") go through the hash, which is an
HMAC with a server-side secret, so a leaked database does not give an attacker a table of ten-digit numbers to reverse.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from fastapi import Depends

from app.core.errors import ApiError
from app.core.settings import Settings, get_settings

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
DEV_PREFIX = "dev:"


def phone_hash(phone_e164: str, settings: Settings) -> str:
    pepper = (settings.phone_pepper or settings.jwt_secret).encode()
    return hmac.new(pepper, phone_e164.encode(), hashlib.sha256).hexdigest()


class PhoneVerifier:
    """token -> verified E.164 phone number, or an ApiError. Replaced in tests."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def verify(self, id_token: str) -> str:
        s = self.settings
        if s.is_dev and id_token.startswith(DEV_PREFIX):
            # Local development only: the app's debug sign-in sends "dev:+91..." with the fixed test code 123456.
            phone = id_token.removeprefix(DEV_PREFIX)
            if not E164.match(phone):
                raise ApiError(401, "invalid_id_token", "The sign-in could not be verified.")
            return phone
        if not s.firebase_credentials_json:
            raise ApiError(503, "phone_auth_unavailable", "Phone sign-in is not set up on this server.")
        try:
            import firebase_admin
            from firebase_admin import auth

            from app.alerts.fcm_client import _certificate

            if not firebase_admin._apps:
                firebase_admin.initialize_app(_certificate(s.firebase_credentials_json))
            claims = auth.verify_id_token(id_token)
        except Exception as exc:  # expired, wrong project, malformed, revoked: all the same answer to the caller
            raise ApiError(401, "invalid_id_token", "The sign-in could not be verified.") from exc
        phone = claims.get("phone_number")
        if not isinstance(phone, str) or not E164.match(phone):
            raise ApiError(401, "invalid_id_token", "The sign-in has no verified phone number.")
        return phone


def phone_verifier_dependency(settings: Settings = Depends(get_settings)) -> PhoneVerifier:
    return PhoneVerifier(settings)

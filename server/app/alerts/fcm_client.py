"""FCM push wrapper (py-pit:http-client-integration pattern).

Wraps firebase-admin behind a small interface so the alert service never
touches the SDK directly, and so tests can inject a fake client without
real Firebase credentials.
"""

import json
import logging
import os
from typing import Protocol

logger = logging.getLogger("satark.alerts.fcm")


class FcmTokenInvalid(Exception):
    """Raised for a stale/unregistered/invalid FCM token. Never propagates past the alert service as a 500."""


class FcmClient(Protocol):
    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> str: ...


REQUIRED_KEYS = ("type", "project_id", "private_key", "client_email")


def _certificate(value: str):
    """Build the firebase_admin credential from SATARK_FIREBASE_CREDENTIALS_JSON.

    The value is the service-account JSON itself (how it is pasted into Render); a path to that file is also accepted for local use.
    firebase_admin's Certificate takes a path or a parsed dict, never JSON text, and its own errors quote the value, which here is a private
    key: every failure below is re-raised with a message that names the problem and never repeats any of the value.
    """
    from firebase_admin import credentials

    text = (value or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            raise RuntimeError("the Firebase credentials are not valid JSON (paste the whole service-account file)") from None
        missing = [k for k in REQUIRED_KEYS if not data.get(k)]
        if missing:
            raise RuntimeError(f"the Firebase credentials are missing: {', '.join(missing)}")
        if data["type"] != "service_account":
            raise RuntimeError("the Firebase credentials must be a service_account key (Firebase console -> Project settings -> Service accounts)")
        source = data
    elif text and "\n" not in text and len(text) < 1024 and os.path.isfile(text):
        source = text
    else:
        raise RuntimeError("the Firebase credentials are neither the service-account JSON nor the path of an existing file")
    try:
        return credentials.Certificate(source)
    except (ValueError, OSError):
        raise RuntimeError("the Firebase service-account key could not be read (is the private key complete?)") from None


def check_credentials_json(value: str) -> None:
    """Raise RuntimeError if a non-empty value cannot be used. Empty is fine: it means the local stub is used."""
    if value and value.strip():
        _certificate(value)


class FirebaseFcmClient:
    def __init__(self, credentials_json: str):
        import firebase_admin

        if not firebase_admin._apps:
            firebase_admin.initialize_app(_certificate(credentials_json))

    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> str:
        from firebase_admin import messaging
        from firebase_admin.exceptions import NotFoundError, InvalidArgumentError

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data,
            token=token,
        )
        try:
            return messaging.send(message)
        except (NotFoundError, InvalidArgumentError) as exc:
            raise FcmTokenInvalid(str(exc)) from exc


class LocalStubFcmClient:
    """Used when Firebase credentials aren't configured (dev/test)."""

    def __init__(self, invalid_tokens: frozenset[str] = frozenset()):
        self._invalid_tokens = invalid_tokens

    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> str:
        if not token or token in self._invalid_tokens:
            raise FcmTokenInvalid(f"stale or invalid token: {token!r}")
        return f"stub-message-{hash((token, title)) & 0xffffffff:x}"


def get_fcm_client(credentials_json: str) -> FcmClient:
    if credentials_json:
        return FirebaseFcmClient(credentials_json)
    return LocalStubFcmClient()

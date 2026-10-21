"""FCM push wrapper (py-pit:http-client-integration pattern).

Wraps firebase-admin behind a small interface so the alert service never
touches the SDK directly, and so tests can inject a fake client without
real Firebase credentials.
"""

import logging
from typing import Protocol

logger = logging.getLogger("satark.alerts.fcm")


class FcmTokenInvalid(Exception):
    """Raised for a stale/unregistered/invalid FCM token. Never propagates past the alert service as a 500."""


class FcmClient(Protocol):
    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> str: ...


class FirebaseFcmClient:
    def __init__(self, credentials_json: str):
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate_from_json(credentials_json) if hasattr(
                credentials, "Certificate_from_json"
            ) else credentials.Certificate(credentials_json)
            firebase_admin.initialize_app(cred)

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

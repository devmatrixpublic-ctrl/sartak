"""Startup validation of the auth-related settings. Called from create_app()."""
from __future__ import annotations

from pathlib import Path

from app.core.settings import DEV_JWT_SECRET, Settings

MIN_SECRET_BYTES = 32


def expected_signing_digests(settings: Settings) -> frozenset[str]:
    return frozenset(d.strip().lower() for d in settings.auth_expected_signing_sha256.split(",") if d.strip())


def validate_auth_settings(settings: Settings) -> None:
    """Fail at boot, not on the first request. Dev is permissive; everything else is strict."""
    if settings.auth_enable_dev_token and not settings.is_dev:
        raise RuntimeError("SATARK_AUTH_ENABLE_DEV_TOKEN is only allowed when SATARK_ENV=dev")
    if settings.is_dev:
        return
    if settings.jwt_secret == DEV_JWT_SECRET or len(settings.jwt_secret.encode()) < MIN_SECRET_BYTES:
        raise RuntimeError(f"SATARK_JWT_SECRET must be set to a real secret of at least {MIN_SECRET_BYTES} bytes")
    if not settings.auth_require_hardware:
        raise RuntimeError("non-dev environments must require hardware-backed attestation")
    if not settings.auth_expected_package or not expected_signing_digests(settings):
        raise RuntimeError("non-dev environments need SATARK_AUTH_EXPECTED_PACKAGE and _SIGNING_SHA256")
    if not settings.auth_attestation_roots or not Path(settings.auth_attestation_roots).is_file():
        raise RuntimeError("non-dev environments need SATARK_AUTH_ATTESTATION_ROOTS pointing at the pinned Google roots")

"""Google's attestation certificate revocation status list, cached.

Fail closed: if the list has never been fetched and the fetch fails, registration is refused
(503). A stale cached list is served for up to MAX_STALE_S so a Google outage does not lock
every phone out of re-registering.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from .errors import AuthError

STATUS_URL = "https://android.googleapis.com/attestation/status"
MAX_STALE_S = 24 * 3600

RevokedSerials = Callable[[], frozenset[str]]


def parse_status(doc: dict[str, Any]) -> frozenset[str]:
    entries = doc.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("status list has no entries")
    return frozenset(str(k).lower().lstrip("0") or "0" for k in entries)


def _default_fetch() -> dict[str, Any]:
    import httpx

    r = httpx.get(STATUS_URL, timeout=5.0)
    r.raise_for_status()
    return r.json()


class GoogleRevocationList:
    def __init__(
        self,
        fetch: Callable[[], dict[str, Any]] = _default_fetch,
        ttl_s: int = 3600,
        clock: Callable[[], float] = time.time,
    ):
        self._fetch = fetch
        self._ttl = ttl_s
        self._clock = clock
        self._cache: frozenset[str] | None = None
        self._fetched_at = 0.0

    def __call__(self) -> frozenset[str]:
        now = self._clock()
        age = now - self._fetched_at
        if self._cache is not None and age < self._ttl:
            return self._cache
        try:
            self._cache = parse_status(self._fetch())
            self._fetched_at = now
        except Exception:
            if self._cache is None or age > MAX_STALE_S:
                raise AuthError(503, "attestation_unavailable",
                                "Could not check certificate revocation status; try again shortly.")
        return self._cache


def serial_key(serial: int) -> str:
    """Google lists serials as lowercase hex without leading zeros."""
    return f"{serial:x}"

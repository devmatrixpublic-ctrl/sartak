"""Fixed-window rate limiting. Redis in deploy (shared across instances), memory in dev/tests.

Redis holds counters only, never payment or session state (see README). If Redis is down the
limiter fails OPEN and logs: rate limiting is abuse control, not authentication, and the design
rule is that infrastructure trouble must never block a payment.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Protocol

logger = logging.getLogger("satark.auth.ratelimit")


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        """Count one request. Returns (allowed, retry_after_seconds)."""


class InMemoryRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}   # key -> (window_start, count)

    def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        now = self._clock()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= window_s:
                start, count = now, 0
            count += 1
            self._windows[key] = (start, count)
            if count > limit:
                return False, max(1, int(start + window_s - now))
            return True, 0


class RedisRateLimiter:
    """INCR + EXPIRE on first hit. `client` is a redis.Redis."""

    def __init__(self, client):
        self._r = client

    def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if ttl < 0:                      # first hit, or a key that lost its expiry
            self._r.expire(key, window_s)
            ttl = window_s
        if count > limit:
            return False, max(1, int(ttl))
        return True, 0


class FailOpenLimiter:
    def __init__(self, inner: RateLimiter):
        self._inner = inner

    def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        try:
            return self._inner.hit(key, limit, window_s)
        except Exception:
            logger.warning("rate limiter backend unavailable; allowing request", exc_info=True)
            return True, 0


_limiter: RateLimiter | None = None


def get_rate_limiter(settings) -> RateLimiter:
    global _limiter
    if _limiter is None:
        if settings.is_dev:
            _limiter = InMemoryRateLimiter()
        else:
            import redis

            _limiter = FailOpenLimiter(RedisRateLimiter(redis.Redis.from_url(settings.redis_url)))
    return _limiter


def reset_rate_limiter() -> None:
    global _limiter
    _limiter = None

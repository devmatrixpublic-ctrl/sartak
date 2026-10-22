"""Rate limiter logic. RedisRateLimiter is tested against a fake that mimics the three Redis commands it
uses (INCR, TTL, EXPIRE inside a pipeline). That proves our logic, NOT behaviour against a real Redis;
run it against the Render Key Value instance before relying on it."""
import logging

import pytest

from app.auth.ratelimit import (FailOpenLimiter, InMemoryRateLimiter, RedisRateLimiter, get_rate_limiter,
                                reset_rate_limiter)
from app.core.settings import Settings


class FakeRedis:
    def __init__(self, clock):
        self.clock = clock
        self.values: dict[str, int] = {}
        self.expires: dict[str, float] = {}

    def _expire_if_due(self, key):
        if key in self.expires and self.clock() >= self.expires[key]:
            self.values.pop(key, None)
            self.expires.pop(key, None)

    def pipeline(self):
        outer = self
        queued = []

        class Pipe:
            def incr(self, key):
                queued.append(("incr", key))

            def ttl(self, key):
                queued.append(("ttl", key))

            def execute(self):
                out = []
                for op, key in queued:
                    outer._expire_if_due(key)
                    if op == "incr":
                        outer.values[key] = outer.values.get(key, 0) + 1
                        out.append(outer.values[key])
                    else:
                        out.append(int(outer.expires[key] - outer.clock()) if key in outer.expires else -1)
                return out

        return Pipe()

    def expire(self, key, seconds):
        self.expires[key] = self.clock() + seconds


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.mark.parametrize("make", ["memory", "redis"])
def test_allows_up_to_the_limit_then_blocks_with_retry_after_then_recovers(make):
    clock = Clock()
    limiter = InMemoryRateLimiter(clock) if make == "memory" else RedisRateLimiter(FakeRedis(clock))
    results = [limiter.hit("k", 3, 60) for _ in range(5)]
    assert [r[0] for r in results] == [True, True, True, False, False]
    assert 1 <= results[3][1] <= 60
    clock.t += 61
    assert limiter.hit("k", 3, 60) == (True, 0)


@pytest.mark.parametrize("make", ["memory", "redis"])
def test_keys_are_independent(make):
    clock = Clock()
    limiter = InMemoryRateLimiter(clock) if make == "memory" else RedisRateLimiter(FakeRedis(clock))
    for _ in range(3):
        limiter.hit("a", 3, 60)
    assert limiter.hit("a", 3, 60)[0] is False
    assert limiter.hit("b", 3, 60)[0] is True


def test_redis_limiter_sets_an_expiry_on_the_first_hit_so_keys_cannot_live_forever():
    clock = Clock()
    fake = FakeRedis(clock)
    RedisRateLimiter(fake).hit("k", 5, 60)
    assert fake.expires["k"] == clock.t + 60


def test_redis_limiter_repairs_a_key_that_lost_its_expiry():
    clock = Clock()
    fake = FakeRedis(clock)
    fake.values["k"] = 2                                   # e.g. EXPIRE failed earlier
    RedisRateLimiter(fake).hit("k", 5, 60)
    assert "k" in fake.expires


def test_fail_open_limiter_allows_and_logs_when_the_backend_is_down(caplog):
    class Down:
        def hit(self, *a):
            raise ConnectionError("redis is down")

    with caplog.at_level(logging.WARNING, logger="satark.auth.ratelimit"):
        assert FailOpenLimiter(Down()).hit("k", 1, 60) == (True, 0)
    assert "allowing request" in caplog.text


def test_dev_uses_memory_and_production_wraps_redis_fail_open(monkeypatch):
    import redis

    reset_rate_limiter()
    assert isinstance(get_rate_limiter(Settings(env="dev")), InMemoryRateLimiter)
    reset_rate_limiter()
    seen = {}

    def fake_from_url(url, *a, **k):
        seen["url"] = url
        return FakeRedis(Clock())

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(fake_from_url))
    limiter = get_rate_limiter(Settings(env="production", redis_url="redis://cache:6379/0"))
    assert isinstance(limiter, FailOpenLimiter) and seen["url"] == "redis://cache:6379/0"
    assert get_rate_limiter(Settings(env="production")) is limiter            # cached
    reset_rate_limiter()

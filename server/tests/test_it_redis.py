"""RedisRateLimiter against a real Redis (CI service container; skipped without SATARK_TEST_REDIS_URL).

The unit tests prove our logic against a fake. These prove the two things a fake cannot: the real command
semantics (INCR/TTL/EXPIRE in a pipeline) and that the counter is atomic under concurrent callers.
"""
import os
import threading
import time
import uuid

import pytest

from app.auth.ratelimit import FailOpenLimiter, RedisRateLimiter, get_rate_limiter, reset_rate_limiter
from app.core.settings import Settings

REDIS_URL = os.environ.get("SATARK_TEST_REDIS_URL", "")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="set SATARK_TEST_REDIS_URL to run against Redis")


@pytest.fixture
def client():
    import redis

    c = redis.Redis.from_url(REDIS_URL)
    c.ping()
    return c


@pytest.fixture
def key():
    return f"it:{uuid.uuid4().hex}"


def test_allows_the_limit_then_blocks_then_recovers_after_the_real_window(client, key):
    limiter = RedisRateLimiter(client)
    results = [limiter.hit(key, 3, 2) for _ in range(5)]
    assert [r[0] for r in results] == [True, True, True, False, False]
    assert 1 <= results[3][1] <= 2
    time.sleep(2.3)                                              # the real TTL expires the key
    assert limiter.hit(key, 3, 2) == (True, 0)


def test_the_first_hit_sets_a_real_expiry(client, key):
    RedisRateLimiter(client).hit(key, 5, 60)
    assert 0 < client.ttl(key) <= 60


def test_a_key_that_lost_its_expiry_is_repaired(client, key):
    client.set(key, 2)                                           # no TTL: what a failed EXPIRE would leave behind
    assert client.ttl(key) == -1
    RedisRateLimiter(client).hit(key, 5, 60)
    assert client.ttl(key) > 0


def test_keys_are_independent(client, key):
    limiter = RedisRateLimiter(client)
    for _ in range(3):
        limiter.hit(key + ":a", 3, 30)
    assert limiter.hit(key + ":a", 3, 30)[0] is False
    assert limiter.hit(key + ":b", 3, 30)[0] is True


def test_the_limit_holds_under_concurrent_callers(client, key):
    limiter = RedisRateLimiter(client)
    results, barrier = [], threading.Barrier(40)

    def worker():
        barrier.wait(timeout=10)
        results.append(limiter.hit(key, 10, 30)[0])

    threads = [threading.Thread(target=worker) for _ in range(40)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert len(results) == 40 and results.count(True) == 10 and results.count(False) == 30


def test_fail_open_when_redis_is_unreachable_and_fast(key):
    import redis

    dead = redis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.3, socket_timeout=0.3)
    started = time.time()
    assert FailOpenLimiter(RedisRateLimiter(dead)).hit(key, 1, 60) == (True, 0)
    assert time.time() - started < 5


def test_production_wiring_builds_a_working_limiter_from_settings(key):
    reset_rate_limiter()
    try:
        limiter = get_rate_limiter(Settings(env="production", redis_url=REDIS_URL))
        assert isinstance(limiter, FailOpenLimiter)
        assert [limiter.hit(key, 2, 30)[0] for _ in range(3)] == [True, True, False]
    finally:
        reset_rate_limiter()

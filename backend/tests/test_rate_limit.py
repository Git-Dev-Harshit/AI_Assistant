import os

import pytest
from redis.asyncio import Redis

from app.services.rate_limit import InMemoryRateLimiter, RedisRateLimiter

QUESTION = {"question": "How do refunds work?"}


async def test_ask_is_rate_limited_per_client_with_retry_after(client, settings):
    headers = {"X-Client-Id": "client-aaaaaaaa"}
    for _ in range(settings.ask_rate_limit_per_minute):
        assert (await client.post("/ask", json=QUESTION, headers=headers)).status_code == 200

    response = await client.post("/ask", json=QUESTION, headers=headers)

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    error = response.json()["error"]
    assert error["code"] == "RATE_LIMITED"
    assert error["details"]["retry_after_seconds"] == int(response.headers["Retry-After"])


async def test_rate_limit_headers_are_returned(client, settings):
    response = await client.post("/ask", json=QUESTION, headers={"X-Client-Id": "client-bbbbbbbb"})

    assert response.headers["X-RateLimit-Limit"] == str(settings.ask_rate_limit_per_minute)
    assert response.headers["X-RateLimit-Remaining"] == str(settings.ask_rate_limit_per_minute - 1)


async def test_limits_are_independent_per_client(client, settings):
    for _ in range(settings.ask_rate_limit_per_minute + 1):
        await client.post("/ask", json=QUESTION, headers={"X-Client-Id": "client-cccccccc"})

    response = await client.post("/ask", json=QUESTION, headers={"X-Client-Id": "client-dddddddd"})

    assert response.status_code == 200


async def test_other_endpoints_are_not_rate_limited(client, settings):
    for _ in range(settings.ask_rate_limit_per_minute + 2):
        assert (await client.get("/documents")).status_code == 200


async def test_in_memory_window_resets():
    now = [1_000.0]
    limiter = InMemoryRateLimiter(limit=2, window_s=60, clock=lambda: now[0])

    assert (await limiter.hit("k")).allowed
    assert (await limiter.hit("k")).allowed
    blocked = await limiter.hit("k")
    assert not blocked.allowed
    assert blocked.retry_after_s == 20  # 1000 % 60 = 40s into the window

    now[0] += blocked.retry_after_s
    assert (await limiter.hit("k")).allowed


async def test_redis_outage_fails_open():
    unreachable = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
    limiter = RedisRateLimiter(unreachable, limit=1, fail_open=True)

    try:
        assert (await limiter.hit("k")).allowed
        assert (await limiter.hit("k")).allowed
    finally:
        await unreachable.aclose()


async def test_redis_outage_fails_closed_when_configured(client, services):
    unreachable = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
    services.rate_limiter = RedisRateLimiter(unreachable, limit=5, fail_open=False)

    try:
        response = await client.post("/ask", json=QUESTION)
    finally:
        await unreachable.aclose()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RATE_LIMITER_UNAVAILABLE"


@pytest.mark.skipif(not os.environ.get("TEST_REDIS_URL"), reason="TEST_REDIS_URL not set")
async def test_redis_limiter_counts_across_instances():
    redis = Redis.from_url(os.environ["TEST_REDIS_URL"])
    try:
        await redis.flushdb()
        # Two limiter objects sharing one Redis = two API instances behind a load balancer.
        instance_a = RedisRateLimiter(redis, limit=3, prefix="test")
        instance_b = RedisRateLimiter(redis, limit=3, prefix="test")

        results = [await instance_a.hit("user"), await instance_b.hit("user"), await instance_a.hit("user")]
        assert all(r.allowed for r in results)
        assert not (await instance_b.hit("user")).allowed
    finally:
        await redis.flushdb()
        await redis.aclose()

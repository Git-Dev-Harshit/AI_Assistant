"""Fixed-window rate limiting for POST /ask.

`RedisRateLimiter` is the default: counters live in Redis, so the limit holds across any
number of API instances behind a load balancer. `InMemoryRateLimiter` is for tests and
single-process runs without Redis.

Algorithm: one counter per (client, window). INCR + EXPIRE run in a single MULTI/EXEC
transaction, so concurrent requests cannot race past the limit. Retry-After is the time
left in the current window. Trade-off: a client can burst up to 2x the limit across a
window boundary; a sliding-window or token-bucket (Lua) script removes that if needed.
"""

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_s: int  # seconds until the current window resets


class RateLimiter(Protocol):
    limit: int

    async def hit(self, key: str) -> RateLimitDecision: ...


class RedisRateLimiter:
    def __init__(
        self,
        redis: Redis,
        limit: int,
        window_s: int = 60,
        *,
        fail_open: bool = True,
        prefix: str = "ratelimit:ask",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.limit = limit
        self._redis = redis
        self._window_s = window_s
        self._fail_open = fail_open
        self._prefix = prefix
        self._clock = clock

    async def hit(self, key: str) -> RateLimitDecision:
        now = self._clock()
        window = int(now // self._window_s)
        redis_key = f"{self._prefix}:{key}:{window}"
        retry_after = _seconds_left(now, self._window_s)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, self._window_s + 1)
                count, _ = await pipe.execute()
        except RedisError as exc:
            # Availability over strictness: a Redis outage should not take /ask down.
            # Set RATE_LIMIT_FAIL_OPEN=false to reject instead when abuse is the bigger risk.
            logger.warning("rate_limiter_unavailable", error=type(exc).__name__, fail_open=self._fail_open)
            if self._fail_open:
                return RateLimitDecision(True, self.limit, self.limit, retry_after)
            raise
        return _decision(int(count), self.limit, retry_after)


class InMemoryRateLimiter:
    """Per-process counters. Correct for a single instance only."""

    def __init__(self, limit: int, window_s: int = 60, clock: Callable[[], float] = time.time) -> None:
        self.limit = limit
        self._window_s = window_s
        self._clock = clock
        self._window = -1
        self._counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str) -> RateLimitDecision:
        now = self._clock()
        window = int(now // self._window_s)
        async with self._lock:
            if window != self._window:  # new window: drop old counters, memory stays bounded
                self._window, self._counts = window, {}
            count = self._counts.get(key, 0) + 1
            self._counts[key] = count
        return _decision(count, self.limit, _seconds_left(now, self._window_s))


def _seconds_left(now: float, window_s: int) -> int:
    return max(1, math.ceil(window_s - (now % window_s)))


def _decision(count: int, limit: int, retry_after: int) -> RateLimitDecision:
    return RateLimitDecision(
        allowed=count <= limit,
        limit=limit,
        remaining=max(0, limit - count),
        retry_after_s=retry_after,
    )

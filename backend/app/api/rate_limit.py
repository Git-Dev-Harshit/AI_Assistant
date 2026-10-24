from typing import Annotated

import structlog
from fastapi import Depends, Response
from redis.exceptions import RedisError

from app.api.client import client_identity
from app.api.deps import ServicesDep
from app.core.errors import RateLimitedError, ServiceUnavailableError

logger = structlog.get_logger(__name__)


class RateLimiterUnavailableError(ServiceUnavailableError):
    code = "RATE_LIMITER_UNAVAILABLE"


async def enforce_ask_rate_limit(
    response: Response,
    services: ServicesDep,
    client_id: Annotated[str, Depends(client_identity)],
) -> None:
    """Per-client limit for POST /ask. Raises 429 with Retry-After when exceeded."""
    try:
        decision = await services.rate_limiter.hit(client_id)
    except RedisError as exc:  # only reached when RATE_LIMIT_FAIL_OPEN=false
        raise RateLimiterUnavailableError() from exc

    if not decision.allowed:
        logger.info("rate_limited", limit=decision.limit, retry_after_s=decision.retry_after_s)
        raise RateLimitedError(decision.retry_after_s, limit=decision.limit)

    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)

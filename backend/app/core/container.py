"""Long-lived service objects, created once at startup and shared across requests.

Keeping them in one container makes dependencies explicit and lets tests inject fakes
(see tests/conftest.py) without monkeypatching module globals.
"""

from dataclasses import dataclass

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.device import DeviceInfo, resolve_device
from app.db.session import create_engine, create_session_factory

logger = structlog.get_logger(__name__)


@dataclass
class Services:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis | None
    device: DeviceInfo


async def build_services(settings: Settings) -> Services:
    engine = create_engine(settings)
    redis = (
        Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.redis_timeout_s,
            socket_connect_timeout=settings.redis_timeout_s,
        )
        if settings.redis_url
        else None
    )
    device = resolve_device()
    logger.info("services_ready", device=device.device, device_name=device.name)
    return Services(
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=redis,
        device=device,
    )


async def close_services(services: Services) -> None:
    if services.redis is not None:
        await services.redis.aclose()
    await services.engine.dispose()

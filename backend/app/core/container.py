"""Long-lived service objects, created once at startup and shared across requests.

Keeping them in one container makes dependencies explicit and lets tests inject fakes
(see tests/conftest.py) without monkeypatching module globals.
"""

from dataclasses import dataclass

import anyio
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.device import DeviceInfo, resolve_device
from app.db.models import EMBEDDING_DIM
from app.db.session import create_engine, create_session_factory
from app.services.embeddings import EmbeddingProvider, HashEmbeddings, SentenceTransformerEmbeddings

logger = structlog.get_logger(__name__)


@dataclass
class Services:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis | None
    device: DeviceInfo
    embedder: EmbeddingProvider


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
    device = resolve_device(settings.embedding_device)
    embedder = await _build_embedder(settings, device)
    logger.info(
        "services_ready",
        device=device.device,
        device_name=device.name,
        embedding_provider=embedder.name,
        embedding_model=embedder.model,
    )
    return Services(
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=redis,
        device=device,
        embedder=embedder,
    )


async def _build_embedder(settings: Settings, device: DeviceInfo) -> EmbeddingProvider:
    if settings.embedding_provider == "hash":
        logger.warning("using_hash_embeddings", note="demo/test fallback, lexical matching only")
        return HashEmbeddings(EMBEDDING_DIM)
    # Loading the model takes a few seconds; do it off the event loop.
    return await anyio.to_thread.run_sync(
        lambda: SentenceTransformerEmbeddings(
            settings.embedding_model,
            device,
            expected_dim=EMBEDDING_DIM,
            query_instruction=settings.embedding_query_instruction,
            max_concurrency=settings.embedding_max_concurrency,
        )
    )


async def close_services(services: Services) -> None:
    if services.redis is not None:
        await services.redis.aclose()
    await services.engine.dispose()

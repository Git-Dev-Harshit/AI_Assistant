import os
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.container import Services
from app.core.device import DeviceInfo
from app.db.models import EMBEDDING_DIM, Base
from app.db.session import create_session_factory
from app.main import create_app
from app.services.embeddings import HashEmbeddings
from app.services.llm import Prompt

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://knowledge:knowledge@localhost:5433/knowledge_test"
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        log_level="WARNING",
        database_url=TEST_DATABASE_URL,
        redis_url=None,
        # Must match the providers injected in `services` below.
        embedding_provider="hash",
        llm_provider="mock",
    )


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A clean schema for every test (tables are created once, then truncated)."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    yield engine
    await engine.dispose()


class FakeLLM:
    """Records prompts; returns a configurable answer or raises a configured error."""

    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.answer = "Refunds are available within 30 days [1]."
        self.error: Exception | None = None
        self.health_status = "ok"
        self.prompts: list[Prompt] = []

    async def generate(self, prompt: Prompt) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.answer

    async def health(self) -> str:
        return self.health_status

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def services(engine: AsyncEngine, fake_llm: FakeLLM) -> Services:
    return Services(
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=None,
        device=DeviceInfo("cpu", "CPU"),
        embedder=HashEmbeddings(EMBEDDING_DIM),
        llm=fake_llm,
    )


@pytest.fixture
async def client(settings: Settings, services: Services) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, services)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

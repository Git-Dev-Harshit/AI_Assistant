import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.errors import DatabaseUnavailableError


def create_engine(settings: Settings) -> AsyncEngine:
    """Async engine with a bounded connection pool and server-side statement timeout.

    - `pool_size`/`max_overflow` cap connections per process, protecting PostgreSQL.
    - `pool_timeout` fails fast (-> 503) instead of queueing forever when the pool is exhausted.
    - `statement_timeout` stops runaway queries on the server side.
    """
    url = make_url(settings.database_url)
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    server_settings = {"statement_timeout": str(settings.db_statement_timeout_ms)}

    async def connect() -> asyncpg.Connection:
        try:
            return await asyncpg.connect(dsn, timeout=settings.db_pool_timeout_s, server_settings=server_settings)
        except (OSError, TimeoutError) as exc:
            # Refused connection, unknown host (e.g. the DB container is down) or connect
            # timeout. SQLAlchemy passes these through unwrapped, so translate them here,
            # where they can only mean "database unreachable".
            raise DatabaseUnavailableError() from exc

    return create_async_engine(
        url,
        async_creator=connect,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

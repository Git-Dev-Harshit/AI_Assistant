from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Async engine with a bounded connection pool and server-side statement timeout.

    - `pool_size`/`max_overflow` cap connections per process, protecting PostgreSQL.
    - `pool_timeout` fails fast (-> 503) instead of queueing forever when the pool is exhausted.
    - `statement_timeout` stops runaway queries on the server side.
    """
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.db_pool_timeout_s,
            "server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)},
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

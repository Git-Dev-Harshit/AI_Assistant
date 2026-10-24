from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import documents, health
from app.core.config import Settings, get_settings
from app.core.container import Services, build_services, close_services
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """Application factory.

    `services` can be injected (tests do this); otherwise they are built in the lifespan
    handler at startup and closed at shutdown.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is not None:
            yield
            return
        app.state.services = await build_services(settings)
        try:
            yield
        finally:
            await close_services(app.state.services)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Add knowledge articles and ask grounded questions over them (RAG).",
        lifespan=lifespan,
    )
    app.state.settings = settings
    if services is not None:
        app.state.services = services

    app.add_middleware(RequestContextMiddleware, max_request_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Client-Id", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
    )
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(documents.router)
    return app


app = create_app()

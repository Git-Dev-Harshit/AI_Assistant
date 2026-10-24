import asyncio
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.api.deps import ServicesDep, SettingsDep

router = APIRouter(tags=["health"])

_CHECK_TIMEOUT_S = 2.0


@router.get("/health", summary="Liveness probe")
async def health(services: ServicesDep, settings: SettingsDep) -> dict[str, Any]:
    """Cheap liveness check: the process is up. Does not touch dependencies."""
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "compute": {"device": services.device.device, "name": services.device.name},
    }


@router.get("/ready", summary="Readiness probe (checks dependencies)")
async def ready(services: ServicesDep) -> JSONResponse:
    checks = await _run_checks(services)
    # "disabled" is a valid configuration (e.g. in-memory rate limiting), not a failure.
    healthy = all(value in ("ok", "disabled") for value in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if healthy else "degraded", "checks": checks},
    )


async def _run_checks(services: ServicesDep) -> dict[str, str]:
    async def database() -> str:
        async with services.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"

    async def redis() -> str:
        if services.redis is None:
            return "disabled"
        await services.redis.ping()
        return "ok"

    probes = {"database": database, "redis": redis}
    results: dict[str, str] = {}
    for name, probe in probes.items():
        try:
            results[name] = await asyncio.wait_for(probe(), timeout=_CHECK_TIMEOUT_S)
        except Exception as exc:  # report, don't raise: readiness must always answer
            results[name] = f"error: {type(exc).__name__}"
    return results

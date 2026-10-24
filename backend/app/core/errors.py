"""Application error types and the handlers that turn them into a stable JSON envelope.

Every error response has the same shape:

    {"error": {"code": "SOME_CODE", "message": "Human readable", "request_id": "...", "details": ...}}

`code` is stable and machine-readable; `message` is safe to show to users. Internal details
(stack traces, SQL, upstream URLs, prompts) are only ever logged, never returned.
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        self.headers = headers or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "The request conflicts with the current state of the resource."


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "PAYLOAD_TOO_LARGE"
    message = "The request body is too large."


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many requests. Please slow down."

    def __init__(self, retry_after_s: int, *, limit: int | None = None, message: str | None = None) -> None:
        headers = {"Retry-After": str(retry_after_s)}
        if limit is not None:
            headers |= {"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"}
        super().__init__(message, details={"retry_after_seconds": retry_after_s}, headers=headers)


class ServiceUnavailableError(AppError):
    """A dependency (database, vector store, embedding model, LLM) is unavailable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"
    message = "A required service is temporarily unavailable. Please try again shortly."


class UpstreamTimeoutError(AppError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "UPSTREAM_TIMEOUT"
    message = "An upstream service took too long to respond."


def error_body(code: str, message: str, request_id: str | None, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details is not None:
        body["details"] = details
    return {"error": body}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
}


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    log = logger.error if exc.status_code >= 500 else logger.info
    log("request_failed", status_code=exc.status_code, error_code=exc.code, error=str(exc))
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, _request_id(request), exc.details),
        headers=exc.headers,
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Deliberately omit the rejected `input` values: they may be large or sensitive.
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body") or "body",
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type"),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_body("VALIDATION_ERROR", "The request is invalid.", _request_id(request), details),
    )


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, _request_id(request)),
        headers=getattr(exc, "headers", None),
    )


async def _database_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the driver error for diagnosis; never return connection details to the client.
    logger.error("database_error", error_type=type(exc).__name__, error=str(exc)[:500])
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=error_body(
            "DATABASE_UNAVAILABLE",
            "The database is temporarily unavailable. Please try again shortly.",
            _request_id(request),
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    # Database connectivity problems (refused connection, pool exhausted, statement timeout).
    for exc_type in (OperationalError, DBAPIError, SQLAlchemyTimeoutError, ConnectionRefusedError):
        app.add_exception_handler(exc_type, _database_error_handler)

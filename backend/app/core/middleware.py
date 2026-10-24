import re
import time
import uuid

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.errors import error_body

logger = structlog.get_logger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, enforces the body size limit, logs every request and
    converts any unhandled exception into a generic 500 envelope (no stack traces leak)."""

    def __init__(self, app: FastAPI, max_request_bytes: int) -> None:
        super().__init__(app)
        self.max_request_bytes = max_request_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()

        response = self._reject_oversized(request, request_id)
        if response is None:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("unhandled_exception", method=request.method, path=request.url.path)
                response = JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content=error_body("INTERNAL_ERROR", "An unexpected error occurred.", request_id),
                )

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response

    def _reject_oversized(self, request: Request, request_id: str) -> Response | None:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_request_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content=error_body(
                    "PAYLOAD_TOO_LARGE",
                    f"Request body exceeds the {self.max_request_bytes} byte limit.",
                    request_id,
                ),
            )
        return None

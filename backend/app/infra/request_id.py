from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((perf_counter() - started_at) * 1000)
            logger.exception("api.request_failed", duration_ms=duration_ms)
            raise
        else:
            duration_ms = int((perf_counter() - started_at) * 1000)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "api.request_completed",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainError,
    EntityNotFoundError,
    UnsupportedMarketplaceError,
)

logger = structlog.get_logger(__name__)


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": details,
                    "request_id": request_id,
                }
            }
        ),
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(
        request: Request,
        exc: EntityNotFoundError,
    ) -> JSONResponse:
        _log_business_error(request, exc, status_code=404, code="not_found")
        return error_response(404, "not_found", str(exc), request_id=_request_id(request))

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request,
        exc: AuthenticationError,
    ) -> JSONResponse:
        _log_business_error(request, exc, status_code=401, code="unauthorized")
        return error_response(
            401,
            "unauthorized",
            str(exc),
            request_id=_request_id(request),
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        request: Request,
        exc: AuthorizationError,
    ) -> JSONResponse:
        _log_business_error(request, exc, status_code=403, code="forbidden")
        return error_response(403, "forbidden", str(exc), request_id=_request_id(request))

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
        _log_business_error(request, exc, status_code=409, code="conflict")
        return error_response(409, "conflict", str(exc), request_id=_request_id(request))

    @app.exception_handler(UnsupportedMarketplaceError)
    async def unsupported_marketplace_handler(
        request: Request,
        exc: UnsupportedMarketplaceError,
    ) -> JSONResponse:
        _log_business_error(
            request,
            exc,
            status_code=422,
            code="unsupported_marketplace",
        )
        return error_response(
            422,
            "unsupported_marketplace",
            str(exc),
            request_id=_request_id(request),
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        _log_business_error(request, exc, status_code=400, code="domain_error")
        return error_response(400, "domain_error", str(exc), request_id=_request_id(request))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.info(
            "api.business_error",
            error_kind="business",
            error_code="validation_error",
            status_code=422,
            details=exc.errors(),
        )
        return error_response(
            422,
            "validation_error",
            "Request validation failed",
            details=exc.errors(),
            request_id=_request_id(request),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        code = _http_error_code(exc.status_code)
        if exc.status_code >= 500:
            logger.error(
                "api.technical_error",
                error_kind="technical",
                error_code=code,
                status_code=exc.status_code,
                details=None if isinstance(exc.detail, str) else exc.detail,
            )
        else:
            logger.info(
                "api.business_error",
                error_kind="business",
                error_code=code,
                status_code=exc.status_code,
                details=None if isinstance(exc.detail, str) else exc.detail,
            )
        return error_response(
            exc.status_code,
            code,
            detail,
            details=None if isinstance(exc.detail, str) else exc.detail,
            request_id=_request_id(request),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "api.technical_error",
            error_kind="technical",
            error_code=exc.__class__.__name__,
            status_code=500,
        )
        return error_response(
            500,
            "internal_error",
            "Internal server error",
            request_id=_request_id(request),
        )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or request.headers.get("x-request-id")


def _log_business_error(
    request: Request,
    exc: Exception,
    *,
    status_code: int,
    code: str,
) -> None:
    logger.info(
        "api.business_error",
        error_kind="business",
        error_code=code,
        error_type=exc.__class__.__name__,
        status_code=status_code,
        request_id=_request_id(request),
    )


def _http_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "validation_error",
        429: "too_many_requests",
    }.get(status_code, "http_error")

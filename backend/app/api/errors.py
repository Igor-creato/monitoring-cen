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
        return error_response(404, "not_found", str(exc), request_id=_request_id(request))

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request,
        exc: AuthenticationError,
    ) -> JSONResponse:
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
        return error_response(403, "forbidden", str(exc), request_id=_request_id(request))

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return error_response(409, "conflict", str(exc), request_id=_request_id(request))

    @app.exception_handler(UnsupportedMarketplaceError)
    async def unsupported_marketplace_handler(
        request: Request,
        exc: UnsupportedMarketplaceError,
    ) -> JSONResponse:
        return error_response(
            422,
            "unsupported_marketplace",
            str(exc),
            request_id=_request_id(request),
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(400, "domain_error", str(exc), request_id=_request_id(request))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
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
        return error_response(
            exc.status_code,
            _http_error_code(exc.status_code),
            detail,
            details=None if isinstance(exc.detail, str) else exc.detail,
            request_id=_request_id(request),
            headers=exc.headers,
        )


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id")


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

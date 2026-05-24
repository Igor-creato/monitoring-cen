from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.errors import install_error_handlers
from app.api.v1.router import router as v1_router
from app.infra.config import get_settings
from app.infra.db.session import async_session_factory
from app.infra.logging import configure_logging
from app.infra.metrics import collect_metrics
from app.infra.redis import create_redis_client
from app.infra.request_id import RequestIDMiddleware
from app.web.router import (
    WebRedirect,
    static_directory,
    web_redirect_handler,
)
from app.web.router import (
    router as web_router,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        description="MVP API for monitoring product prices by URL.",
    )

    app.add_middleware(RequestIDMiddleware)
    install_error_handlers(app)
    app.add_exception_handler(WebRedirect, web_redirect_handler)
    app.mount("/static", StaticFiles(directory=static_directory), name="static")
    app.include_router(web_router)
    app.include_router(v1_router)
    app.include_router(v1_router, prefix="/api/v1", include_in_schema=False)

    @app.get(
        "/health",
        tags=["health"],
        summary="Health check",
        description="Returns service liveness status.",
    )
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/ready",
        tags=["health"],
        summary="Readiness check",
        description="Checks required runtime dependencies.",
    )
    async def ready() -> JSONResponse:
        checks: dict[str, str] = {}
        ready_status = True

        try:
            async with async_session_factory() as session:
                await session.execute(text("select 1"))
            checks["database"] = "ok"
        except Exception:
            ready_status = False
            checks["database"] = "error"

        redis = create_redis_client()
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            ready_status = False
            checks["redis"] = "error"
        finally:
            await redis.aclose()

        status_code = 200 if ready_status else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ready" if ready_status else "not_ready", "checks": checks},
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        async with async_session_factory() as session:
            content, media_type = await collect_metrics(session)
        return Response(content=content, media_type=media_type)

    return app


app = create_app()

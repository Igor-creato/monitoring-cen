from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.v1.router import router as v1_router
from app.infra.config import get_settings
from app.infra.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        description="MVP API for monitoring product prices by URL.",
    )

    install_error_handlers(app)
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

    return app


app = create_app()

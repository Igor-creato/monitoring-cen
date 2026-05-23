from typing import Any

from app.infra.config import get_settings
from app.infra.db.session import async_session_factory
from app.infra.http import create_http_client
from app.product_fetching.factory import create_product_provider


async def startup(ctx: dict[str, Any]) -> None:
    ctx["settings"] = get_settings()
    ctx["session_factory"] = async_session_factory
    ctx["http_client"] = create_http_client()
    ctx["product_provider"] = create_product_provider(
        ctx["http_client"],
        settings=ctx["settings"],
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    http_client = ctx.get("http_client")
    if http_client is not None:
        await http_client.aclose()

from typing import Any

from app.infra.config import get_settings
from app.infra.db.session import async_session_factory
from app.infra.http import create_http_client
from app.notifications.registry import create_notification_providers


async def startup(ctx: dict[str, Any]) -> None:
    ctx["settings"] = get_settings()
    ctx["session_factory"] = async_session_factory
    ctx["http_client"] = create_http_client()
    ctx["notification_providers"] = create_notification_providers(ctx["settings"]).as_dict()


async def shutdown(ctx: dict[str, Any]) -> None:
    http_client = ctx.get("http_client")
    if http_client is not None:
        await http_client.aclose()

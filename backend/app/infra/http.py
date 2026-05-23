import httpx

from app.infra.config import get_settings


def create_http_client() -> httpx.AsyncClient:
    settings = get_settings()
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    limits = httpx.Limits(max_connections=settings.http_max_connections)
    return httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True)

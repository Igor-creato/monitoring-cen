from urllib.parse import urlparse

import httpx

from app.domain.enums import Marketplace
from app.parsers.exceptions import ParseMarkupError
from app.parsers.result import ParsedProduct


class WildberriesParser:
    marketplace = Marketplace.WILDBERRIES

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    def supports(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return "wildberries.ru" in host or "wb.ru" in host

    async def parse(self, url: str) -> ParsedProduct:
        raise ParseMarkupError("Wildberries parser is not implemented yet")

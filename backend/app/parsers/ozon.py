from urllib.parse import urlparse

import httpx

from app.domain.enums import Marketplace
from app.parsers.exceptions import ParseMarkupError
from app.parsers.result import ParsedProduct


class OzonParser:
    marketplace = Marketplace.OZON

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    def supports(self, url: str) -> bool:
        return "ozon.ru" in urlparse(url).netloc.lower()

    async def parse(self, url: str) -> ParsedProduct:
        raise ParseMarkupError("Ozon parser is not implemented yet")

import httpx

from app.domain.enums import Marketplace
from app.domain.url_normalization import normalize_product_url
from app.parsers.exceptions import ParseMarkupError
from app.parsers.result import ParsedProduct


class WildberriesParser:
    marketplace = Marketplace.WILDBERRIES

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    def supports(self, url: str) -> bool:
        normalized = normalize_product_url(url)
        return normalized.is_supported and normalized.marketplace == self.marketplace

    async def parse(self, url: str) -> ParsedProduct:
        raise ParseMarkupError("Wildberries parser is not implemented yet")

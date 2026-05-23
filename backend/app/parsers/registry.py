from app.domain.exceptions import UnsupportedMarketplaceError
from app.parsers.base import ProductParser


class ParserRegistry:
    def __init__(self, parsers: list[ProductParser]):
        self._parsers = parsers

    def resolve(self, url: str) -> ProductParser:
        for parser in self._parsers:
            if parser.supports(url):
                return parser
        raise UnsupportedMarketplaceError(f"Unsupported marketplace URL: {url}")

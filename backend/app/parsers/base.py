from typing import Protocol

from app.domain.enums import Marketplace
from app.parsers.result import ParsedProduct


class ProductParser(Protocol):
    marketplace: Marketplace

    def supports(self, url: str) -> bool: ...

    async def parse(self, url: str) -> ParsedProduct: ...

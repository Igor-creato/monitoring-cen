from app.parsers.base import ProductParser
from app.parsers.registry import ParserRegistry


class ParserResolver:
    def __init__(self, registry: ParserRegistry):
        self.registry = registry

    def resolve_by_url(self, url: str) -> ProductParser:
        return self.registry.resolve(url)

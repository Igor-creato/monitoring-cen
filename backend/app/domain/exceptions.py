class DomainError(Exception):
    """Base class for domain-level errors."""


class EntityNotFoundError(DomainError):
    pass


class UnsupportedMarketplaceError(DomainError):
    pass


class ParserError(DomainError):
    pass

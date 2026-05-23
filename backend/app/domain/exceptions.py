class DomainError(Exception):
    """Base class for domain-level errors."""


class EntityNotFoundError(DomainError):
    pass


class AuthenticationError(DomainError):
    pass


class AuthorizationError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class UnsupportedMarketplaceError(DomainError):
    pass


class ParserError(DomainError):
    pass

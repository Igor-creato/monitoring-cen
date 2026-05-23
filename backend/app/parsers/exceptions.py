from app.domain.exceptions import ParserError


class ParseTimeoutError(ParserError):
    pass


class ParseBlockedError(ParserError):
    pass


class ParseMarkupError(ParserError):
    pass

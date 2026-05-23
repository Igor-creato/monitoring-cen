from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class ProductUrl:
    value: str

    def __post_init__(self) -> None:
        parsed = urlparse(self.value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Invalid product URL")

    @property
    def host(self) -> str:
        return urlparse(self.value).netloc.lower()

from decimal import Decimal

from pydantic import BaseModel


class ParsedProduct(BaseModel):
    title: str | None = None
    price: Decimal
    currency: str = "RUB"
    availability: bool | None = None
    raw_url: str

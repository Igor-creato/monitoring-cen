from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.enums import AvailabilityStatus, CheckStatus


class PriceHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    status: CheckStatus
    price: Decimal | None
    old_price: Decimal | None
    currency: str | None
    availability: AvailabilityStatus
    checked_at: datetime


class ProductHistoryResponse(BaseModel):
    product_id: int
    total: int
    limit: int
    offset: int
    items: list[PriceHistoryItem]

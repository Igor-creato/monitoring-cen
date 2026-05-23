from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CheckStatus


class PriceCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    status: CheckStatus
    price: Decimal | None
    currency: str | None
    error_code: str | None
    error_message: str | None
    checked_at: datetime

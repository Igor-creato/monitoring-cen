from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import CheckStatus


@dataclass(slots=True)
class PriceCheck:
    id: int | None
    monitor_id: int
    status: CheckStatus
    checked_at: datetime
    price: Decimal | None = None
    currency: str | None = None
    error_code: str | None = None
    error_message: str | None = None

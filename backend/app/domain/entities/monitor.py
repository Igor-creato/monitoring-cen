from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import Marketplace, MonitorStatus


@dataclass(slots=True)
class Monitor:
    id: int | None
    url: str
    marketplace: Marketplace | None
    status: MonitorStatus
    check_interval_seconds: int
    target_price: Decimal | None = None
    last_price: Decimal | None = None
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None

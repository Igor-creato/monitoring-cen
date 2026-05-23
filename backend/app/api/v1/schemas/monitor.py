from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.domain.enums import Marketplace, MonitorStatus


class MonitorCreateRequest(BaseModel):
    url: HttpUrl
    target_price: Decimal | None = Field(default=None, gt=0)
    check_interval_seconds: int = Field(default=3600, ge=300)
    notification_channel: str | None = None


class MonitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    marketplace: Marketplace | None
    target_price: Decimal | None
    last_price: Decimal | None
    status: MonitorStatus
    check_interval_seconds: int
    last_checked_at: datetime | None
    next_check_at: datetime | None
    created_at: datetime
    updated_at: datetime

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.domain.enums import Marketplace, MonitorStatus


class MonitorCreateRequest(BaseModel):
    url: HttpUrl = Field(description="Product URL from a supported marketplace")
    target_price: Decimal | None = Field(
        default=None,
        gt=0,
        description="Optional target price for notifications",
    )
    check_interval_seconds: int = Field(
        default=3600,
        ge=300,
        le=604800,
        description="Price check interval, from 5 minutes to 7 days",
    )
    notification_channel: str | None = Field(
        default=None,
        max_length=64,
        description="Optional notification channel identifier",
    )


class MonitorUpdateRequest(BaseModel):
    target_price: Decimal | None = Field(default=None, gt=0)
    check_interval_seconds: int | None = Field(default=None, ge=300, le=604800)
    notification_channel: str | None = Field(default=None, max_length=64)
    status: MonitorStatus | None = Field(default=None)


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


class MonitorsListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[MonitorResponse]

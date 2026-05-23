from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.clock import utc_now
from app.domain.enums import AvailabilityStatus, Marketplace


class ProductSnapshot(BaseModel):
    """Provider-neutral representation of the latest product state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    normalized_url: str
    marketplace: Marketplace
    title: str | None = None
    current_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    old_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str | None = None
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    seller_name: str | None = None
    image_url: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=utc_now)
    success: bool = True
    error_code: str | None = None
    error_message: str | None = None

    @field_validator("normalized_url", "title", "currency", "seller_name", "image_url")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.upper()

    @model_validator(mode="after")
    def validate_error_state(self) -> "ProductSnapshot":
        if self.success and (self.error_code or self.error_message):
            raise ValueError("successful product snapshot must not contain error details")
        if not self.success and not self.error_code:
            raise ValueError("failed product snapshot must contain error_code")
        return self

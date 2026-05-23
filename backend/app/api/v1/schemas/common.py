from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MoneySchema(BaseModel):
    amount: Decimal
    currency: str = "RUB"


class TimestampedSchema(OrmModel):
    created_at: datetime
    updated_at: datetime

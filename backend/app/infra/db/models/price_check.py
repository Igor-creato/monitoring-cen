from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import AvailabilityStatus, CheckStatus
from app.infra.db.base import Base
from app.infra.db.types import enum_values, utc_now


class PriceCheckModel(Base):
    __tablename__ = "price_checks"
    __table_args__ = (
        Index("ix_price_checks_source_checked_at", "product_source_id", "checked_at", "id"),
        Index("ix_price_checks_checked_at", "checked_at"),
        Index("ix_price_checks_status_checked_at", "status", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[CheckStatus] = mapped_column(
        Enum(CheckStatus, native_enum=False, values_callable=enum_values),
        nullable=False,
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    availability: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus, native_enum=False, values_callable=enum_values),
        default=AvailabilityStatus.UNKNOWN,
        nullable=False,
    )
    seller_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    monitor = relationship("MonitorModel", back_populates="checks")
    product_source = relationship("ProductSourceModel", back_populates="price_checks")

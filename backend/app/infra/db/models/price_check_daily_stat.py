from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import Base
from app.infra.db.types import utc_now


class PriceCheckDailyStatModel(Base):
    __tablename__ = "price_check_daily_stats"
    __table_args__ = (
        UniqueConstraint(
            "product_source_id",
            "date_day",
            name="uq_price_check_daily_stats_source_day",
        ),
        Index("ix_price_check_daily_stats_source_day", "product_source_id", "date_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_source_id: Mapped[int] = mapped_column(
        ForeignKey("product_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    date_day: Mapped[date] = mapped_column(Date, nullable=False)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    checks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    product_source = relationship("ProductSourceModel")

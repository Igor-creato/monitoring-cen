from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import Marketplace, MonitorStatus
from app.infra.db.base import Base
from app.infra.db.types import enum_values, utc_now


class MonitorModel(Base):
    __tablename__ = "monitors"
    __table_args__ = (
        Index("ix_monitors_status_next_check", "status", "next_check_at", "id"),
        Index("ix_monitors_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    product_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    marketplace: Mapped[Marketplace | None] = mapped_column(
        Enum(Marketplace, native_enum=False, values_callable=enum_values),
        nullable=True,
    )
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[MonitorStatus] = mapped_column(
        Enum(MonitorStatus, native_enum=False, values_callable=enum_values),
        default=MonitorStatus.ACTIVE,
        nullable=False,
    )
    check_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    notification_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("UserModel", back_populates="monitors")
    product_source = relationship("ProductSourceModel", back_populates="monitors")
    checks = relationship("PriceCheckModel", back_populates="monitor")
    notifications = relationship("NotificationModel", back_populates="monitor")
    parser_errors = relationship("ParserErrorModel", back_populates="monitor")

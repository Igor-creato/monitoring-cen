from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import NotificationStatus, NotificationType
from app.infra.db.base import Base
from app.infra.db.types import enum_values, utc_now


class NotificationModel(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "monitor_id",
            "type",
            "channel",
            "dedupe_key",
            name="uq_notifications_dedupe",
        ),
        Index("ix_notifications_status_scheduled", "status", "scheduled_at", "id"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_monitor_created", "monitor_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    price_check_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_checks.id", ondelete="SET NULL"),
        nullable=True,
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        "type",
        Enum(NotificationType, native_enum=False, values_callable=enum_values),
        default=NotificationType.PRICE_CHANGED,
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False, values_callable=enum_values),
        default=NotificationStatus.PENDING,
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    monitor = relationship("MonitorModel", back_populates="notifications")
    user = relationship("UserModel", back_populates="notifications")
    product_source = relationship("ProductSourceModel")
    price_check = relationship("PriceCheckModel")

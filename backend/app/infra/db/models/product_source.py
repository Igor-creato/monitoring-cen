from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import AvailabilityStatus, Marketplace, SourceStatus
from app.infra.db.base import Base
from app.infra.db.types import enum_values, utc_now


class ProductSourceModel(Base):
    __tablename__ = "product_sources"
    __table_args__ = (
        UniqueConstraint(
            "domain",
            "normalized_url_hash",
            name="uq_product_sources_domain_url_hash",
        ),
        UniqueConstraint(
            "marketplace",
            "source_external_id",
            name="uq_product_sources_marketplace_source_external_id",
        ),
        Index("ix_product_sources_product_id", "product_id"),
        Index("ix_product_sources_domain", "domain"),
        Index("ix_product_sources_marketplace", "marketplace"),
        Index("ix_product_sources_status_last_checked", "status", "last_checked_at"),
        Index("ix_product_sources_last_success", "last_success_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    marketplace: Mapped[Marketplace | None] = mapped_column(
        Enum(Marketplace, native_enum=False, values_callable=enum_values),
        nullable=True,
    )
    source_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    availability: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus, native_enum=False, values_callable=enum_values),
        default=AvailabilityStatus.UNKNOWN,
        nullable=False,
    )
    seller_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False, values_callable=enum_values),
        default=SourceStatus.ACTIVE,
        nullable=False,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    product = relationship("ProductModel", back_populates="sources")
    monitors = relationship("MonitorModel", back_populates="product_source")
    price_checks = relationship("PriceCheckModel", back_populates="product_source")
    parser_errors = relationship("ParserErrorModel", back_populates="product_source")

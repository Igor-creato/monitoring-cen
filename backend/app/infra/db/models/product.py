from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import Marketplace
from app.infra.db.base import Base
from app.infra.db.types import utc_now


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint(
            "marketplace",
            "external_product_id",
            name="uq_products_marketplace_external_id",
        ),
        Index("ix_products_marketplace", "marketplace"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    marketplace: Mapped[Marketplace | None] = mapped_column(String(64), nullable=True)
    external_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
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

    sources = relationship("ProductSourceModel", back_populates="product")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import EntityNotFoundError
from app.infra.db.models.monitor import MonitorModel
from app.infra.db.models.product import ProductModel
from app.infra.db.models.product_source import ProductSourceModel


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_raise(self, product_id: int) -> ProductModel:
        result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise EntityNotFoundError(f"Product {product_id} was not found")
        return product

    async def get_for_user_or_raise(self, product_id: int, user_id: int) -> ProductModel:
        result = await self.session.execute(
            select(ProductModel)
            .join(ProductSourceModel)
            .join(MonitorModel)
            .where(ProductModel.id == product_id)
            .where(MonitorModel.user_id == user_id)
            .where(MonitorModel.deleted_at.is_(None))
            .limit(1)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise EntityNotFoundError(f"Product {product_id} was not found")
        return product

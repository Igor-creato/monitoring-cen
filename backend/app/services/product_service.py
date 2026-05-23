from app.infra.db.models.price_check import PriceCheckModel
from app.repositories.price_check_repository import PriceCheckRepository
from app.repositories.product_repository import ProductRepository


class ProductService:
    def __init__(
        self,
        product_repository: ProductRepository,
        price_check_repository: PriceCheckRepository,
    ):
        self.product_repository = product_repository
        self.price_check_repository = price_check_repository

    async def get_history(
        self,
        user_id: int,
        product_id: int,
        limit: int,
        offset: int,
    ) -> tuple[int, list[PriceCheckModel]]:
        await self.product_repository.get_for_user_or_raise(product_id, user_id)
        return await self.price_check_repository.list_by_product_for_user(
            product_id,
            user_id,
            limit,
            offset,
        )

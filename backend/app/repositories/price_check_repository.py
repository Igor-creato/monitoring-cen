from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CheckStatus
from app.infra.db.models.monitor import MonitorModel
from app.infra.db.models.price_check import PriceCheckModel
from app.infra.db.models.product_source import ProductSourceModel


class PriceCheckRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_success(
        self,
        monitor_id: int,
        price: Decimal,
        currency: str,
    ) -> PriceCheckModel:
        check = PriceCheckModel(
            monitor_id=monitor_id,
            status=CheckStatus.SUCCESS,
            price=price,
            currency=currency,
        )
        self.session.add(check)
        await self.session.commit()
        await self.session.refresh(check)
        return check

    async def list_by_product_for_user(
        self,
        product_id: int,
        user_id: int,
        limit: int,
        offset: int,
    ) -> tuple[int, list[PriceCheckModel]]:
        filters = [
            ProductSourceModel.product_id == product_id,
            MonitorModel.user_id == user_id,
            MonitorModel.deleted_at.is_(None),
        ]
        total_result = await self.session.execute(
            select(func.count())
            .select_from(PriceCheckModel)
            .join(
                ProductSourceModel,
                PriceCheckModel.product_source_id == ProductSourceModel.id,
            )
            .join(MonitorModel, PriceCheckModel.monitor_id == MonitorModel.id)
            .where(*filters)
        )
        rows_result = await self.session.execute(
            select(PriceCheckModel)
            .join(
                ProductSourceModel,
                PriceCheckModel.product_source_id == ProductSourceModel.id,
            )
            .join(MonitorModel, PriceCheckModel.monitor_id == MonitorModel.id)
            .where(*filters)
            .order_by(PriceCheckModel.checked_at.desc(), PriceCheckModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return total_result.scalar_one(), list(rows_result.scalars().all())

    async def create_failure(
        self,
        monitor_id: int,
        error_code: str,
        error_message: str,
    ) -> PriceCheckModel:
        check = PriceCheckModel(
            monitor_id=monitor_id,
            status=CheckStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )
        self.session.add(check)
        await self.session.commit()
        await self.session.refresh(check)
        return check

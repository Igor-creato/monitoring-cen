from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CheckStatus
from app.infra.db.models.price_check import PriceCheckModel


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

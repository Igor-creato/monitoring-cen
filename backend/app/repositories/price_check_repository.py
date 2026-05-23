from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CheckStatus
from app.infra.db.models.monitor import MonitorModel
from app.infra.db.models.price_check import PriceCheckModel
from app.infra.db.models.product_source import ProductSourceModel
from app.product_fetching.models import ProductSnapshot


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

    async def add_from_snapshot(
        self,
        *,
        monitor_id: int,
        product_source_id: int | None,
        snapshot: ProductSnapshot,
        status: CheckStatus | None = None,
    ) -> PriceCheckModel:
        check = PriceCheckModel(
            monitor_id=monitor_id,
            product_source_id=product_source_id,
            status=status or _status_from_snapshot(snapshot),
            price=snapshot.current_price,
            old_price=snapshot.old_price,
            currency=snapshot.currency,
            availability=snapshot.availability,
            seller_name=snapshot.seller_name,
            title=snapshot.title,
            error_code=snapshot.error_code,
            error_message=snapshot.error_message,
            checked_at=snapshot.fetched_at,
        )
        self.session.add(check)
        await self.session.flush()
        return check


def _status_from_snapshot(snapshot: ProductSnapshot) -> CheckStatus:
    if snapshot.success and snapshot.current_price is not None:
        return CheckStatus.SUCCESS
    if snapshot.success:
        return CheckStatus.PARSE_ERROR

    error_code = snapshot.error_code or ""
    if "timeout" in error_code:
        return CheckStatus.TIMEOUT
    if error_code in {"captcha_detected", "blocked", "access_denied"}:
        return CheckStatus.BLOCKED
    if "network" in error_code:
        return CheckStatus.NETWORK_ERROR
    return CheckStatus.FAILED

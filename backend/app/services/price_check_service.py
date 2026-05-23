from decimal import Decimal

from app.infra.db.models.price_check import PriceCheckModel
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.price_check_repository import PriceCheckRepository


class PriceCheckService:
    def __init__(
        self,
        monitor_repository: MonitorRepository,
        price_check_repository: PriceCheckRepository,
    ):
        self.monitor_repository = monitor_repository
        self.price_check_repository = price_check_repository

    async def run_check(self, monitor_id: int) -> PriceCheckModel:
        monitor = await self.monitor_repository.get_or_raise(monitor_id)

        return await self.price_check_repository.create_failure(
            monitor_id=monitor.id,
            error_code="parser_not_implemented",
            error_message="Parser integration is not implemented yet",
        )

    def should_notify(self, last_price: Decimal | None, current_price: Decimal) -> bool:
        return last_price is None or current_price != last_price

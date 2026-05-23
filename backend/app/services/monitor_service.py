from app.api.v1.schemas.monitor import MonitorCreateRequest
from app.infra.db.models.monitor import MonitorModel
from app.repositories.monitor_repository import MonitorRepository


class MonitorService:
    def __init__(self, monitor_repository: MonitorRepository):
        self.monitor_repository = monitor_repository

    async def create_monitor(self, payload: MonitorCreateRequest) -> MonitorModel:
        return await self.monitor_repository.create(
            url=str(payload.url),
            target_price=payload.target_price,
            check_interval_seconds=payload.check_interval_seconds,
            notification_channel=payload.notification_channel,
        )

    async def get_monitor(self, monitor_id: int) -> MonitorModel:
        return await self.monitor_repository.get_or_raise(monitor_id)

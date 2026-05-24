from app.api.v1.schemas.monitor import MonitorCreateRequest, MonitorUpdateRequest
from app.domain.enums import MonitorStatus
from app.domain.exceptions import UnsupportedMarketplaceError
from app.domain.url_normalization import normalize_product_url
from app.infra.db.models.monitor import MonitorModel
from app.repositories.monitor_repository import MonitorRepository


class MonitorService:
    def __init__(self, monitor_repository: MonitorRepository):
        self.monitor_repository = monitor_repository

    async def create_monitor(self, user_id: int, payload: MonitorCreateRequest) -> MonitorModel:
        normalized = normalize_product_url(str(payload.url))
        if not normalized.is_supported or normalized.normalized_url is None:
            raise UnsupportedMarketplaceError(
                normalized.reason_if_invalid or "Unsupported marketplace URL"
            )
        if payload.marketplace is not None and payload.marketplace != normalized.marketplace:
            raise UnsupportedMarketplaceError("Ссылка не относится к выбранному маркетплейсу")

        return await self.monitor_repository.create(
            user_id=user_id,
            url=normalized.normalized_url,
            marketplace=normalized.marketplace,
            target_price=payload.target_price,
            check_interval_seconds=payload.check_interval_seconds,
            notification_channel=payload.notification_channel,
        )

    async def list_monitors(
        self,
        user_id: int,
        limit: int,
        offset: int,
        status: MonitorStatus | None = None,
    ) -> tuple[int, list[MonitorModel]]:
        return await self.monitor_repository.list_for_user(user_id, limit, offset, status)

    async def get_monitor(self, user_id: int, monitor_id: int) -> MonitorModel:
        return await self.monitor_repository.get_for_user_or_raise(monitor_id, user_id)

    async def update_monitor(
        self,
        user_id: int,
        monitor_id: int,
        payload: MonitorUpdateRequest,
    ) -> MonitorModel:
        monitor = await self.monitor_repository.get_for_user_or_raise(monitor_id, user_id)
        values = payload.model_dump(exclude_unset=True)
        return await self.monitor_repository.update(monitor, values)

    async def delete_monitor(self, user_id: int, monitor_id: int) -> None:
        monitor = await self.monitor_repository.get_for_user_or_raise(monitor_id, user_id)
        await self.monitor_repository.soft_delete(monitor)

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Marketplace, MonitorStatus
from app.domain.exceptions import EntityNotFoundError
from app.infra.db.models.monitor import MonitorModel


class MonitorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        url: str,
        check_interval_seconds: int,
        marketplace: Marketplace | None = None,
        target_price=None,
        notification_channel: str | None = None,
    ) -> MonitorModel:
        now = datetime.now(UTC)
        monitor = MonitorModel(
            url=url,
            marketplace=marketplace or Marketplace.UNKNOWN,
            target_price=target_price,
            status=MonitorStatus.ACTIVE,
            check_interval_seconds=check_interval_seconds,
            notification_channel=notification_channel,
            next_check_at=now + timedelta(seconds=check_interval_seconds),
        )
        self.session.add(monitor)
        await self.session.commit()
        await self.session.refresh(monitor)
        return monitor

    async def get(self, monitor_id: int) -> MonitorModel | None:
        result = await self.session.execute(
            select(MonitorModel).where(MonitorModel.id == monitor_id)
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, monitor_id: int) -> MonitorModel:
        monitor = await self.get(monitor_id)
        if monitor is None:
            raise EntityNotFoundError(f"Monitor {monitor_id} was not found")
        return monitor

    async def list_due(self, limit: int) -> list[MonitorModel]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(MonitorModel)
            .where(MonitorModel.status == MonitorStatus.ACTIVE)
            .where(MonitorModel.next_check_at <= now)
            .order_by(MonitorModel.next_check_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

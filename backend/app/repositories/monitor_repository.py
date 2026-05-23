from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
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
        user_id: int | None = None,
        marketplace: Marketplace | None = None,
        target_price=None,
        notification_channel: str | None = None,
    ) -> MonitorModel:
        now = datetime.now(UTC)
        monitor = MonitorModel(
            user_id=user_id,
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
            select(MonitorModel)
            .where(MonitorModel.id == monitor_id)
            .where(MonitorModel.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, monitor_id: int) -> MonitorModel:
        monitor = await self.get(monitor_id)
        if monitor is None:
            raise EntityNotFoundError(f"Monitor {monitor_id} was not found")
        return monitor

    async def get_for_user_or_raise(self, monitor_id: int, user_id: int) -> MonitorModel:
        result = await self.session.execute(
            select(MonitorModel)
            .where(MonitorModel.id == monitor_id)
            .where(MonitorModel.user_id == user_id)
            .where(MonitorModel.deleted_at.is_(None))
        )
        monitor = result.scalar_one_or_none()
        if monitor is None:
            raise EntityNotFoundError(f"Monitor {monitor_id} was not found")
        return monitor

    async def list_for_user(
        self,
        user_id: int,
        limit: int,
        offset: int,
        status: MonitorStatus | None = None,
    ) -> tuple[int, list[MonitorModel]]:
        filters = [
            MonitorModel.user_id == user_id,
            MonitorModel.deleted_at.is_(None),
        ]
        if status is not None:
            filters.append(MonitorModel.status == status)

        total_result = await self.session.execute(
            select(func.count()).select_from(MonitorModel).where(*filters)
        )
        rows_result = await self.session.execute(
            select(MonitorModel)
            .where(*filters)
            .order_by(MonitorModel.created_at.desc(), MonitorModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return total_result.scalar_one(), list(rows_result.scalars().all())

    async def update(
        self,
        monitor: MonitorModel,
        values: dict[str, object],
    ) -> MonitorModel:
        now = datetime.now(UTC)
        interval = values.get("check_interval_seconds")

        for field, value in values.items():
            setattr(monitor, field, value)

        if interval is not None:
            monitor.next_check_at = now + timedelta(seconds=int(interval))

        if monitor.status == MonitorStatus.PAUSED:
            monitor.paused_at = monitor.paused_at or now
            monitor.next_check_at = None
        elif monitor.status == MonitorStatus.ACTIVE:
            monitor.paused_at = None
            monitor.next_check_at = monitor.next_check_at or now

        await self.session.commit()
        await self.session.refresh(monitor)
        return monitor

    async def soft_delete(self, monitor: MonitorModel) -> None:
        now = datetime.now(UTC)
        monitor.status = MonitorStatus.DELETED
        monitor.deleted_at = now
        monitor.next_check_at = None
        await self.session.commit()

    async def list_due(self, limit: int) -> list[MonitorModel]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(MonitorModel)
            .where(MonitorModel.status == MonitorStatus.ACTIVE)
            .where(MonitorModel.deleted_at.is_(None))
            .where(MonitorModel.next_check_at <= now)
            .order_by(MonitorModel.next_check_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

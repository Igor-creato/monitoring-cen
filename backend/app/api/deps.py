from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.session import async_session_factory
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.services.monitor_service import MonitorService
from app.services.price_check_service import PriceCheckService


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def get_monitor_repository(
    session: AsyncSession = Depends(get_db_session),
) -> MonitorRepository:
    return MonitorRepository(session)


def get_price_check_repository(
    session: AsyncSession = Depends(get_db_session),
) -> PriceCheckRepository:
    return PriceCheckRepository(session)


def get_notification_repository(
    session: AsyncSession = Depends(get_db_session),
) -> NotificationRepository:
    return NotificationRepository(session)


def get_monitor_service(
    monitor_repository: MonitorRepository = Depends(get_monitor_repository),
) -> MonitorService:
    return MonitorService(monitor_repository)


def get_price_check_service(
    monitor_repository: MonitorRepository = Depends(get_monitor_repository),
    price_check_repository: PriceCheckRepository = Depends(get_price_check_repository),
) -> PriceCheckService:
    return PriceCheckService(monitor_repository, price_check_repository)

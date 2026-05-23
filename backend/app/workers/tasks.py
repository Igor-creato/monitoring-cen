from typing import Any

from app.repositories.monitor_repository import MonitorRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.services.notification_service import NotificationService
from app.services.price_check_service import PriceCheckService


async def run_monitor_check(ctx: dict[str, Any], monitor_id: int) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        service = PriceCheckService(
            monitor_repository=MonitorRepository(session),
            price_check_repository=PriceCheckRepository(session),
        )
        await service.run_check(monitor_id)


async def run_due_monitor_checks(ctx: dict[str, Any]) -> None:
    settings = ctx["settings"]
    redis = ctx["redis"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        repository = MonitorRepository(session)
        monitors = await repository.list_due(settings.check_batch_size)

    for monitor in monitors:
        await redis.enqueue_job("run_monitor_check", monitor.id)


async def send_notification(ctx: dict[str, Any], notification_id: int) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        repository = NotificationRepository(session)
        _ = repository
        service = NotificationService(senders={})
        _ = service
        raise NotImplementedError(
            f"Notification delivery is not implemented yet: {notification_id}"
        )

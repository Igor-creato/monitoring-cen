import hashlib
import json
from typing import Any

import structlog
from arq import Retry

from app.domain.enums import MonitorStatus, NotificationStatus
from app.infra.metrics import observe_notification_send
from app.infra.redis_lock import acquire_redis_lock
from app.notifications.base import NotificationDeliveryError, NotificationSkipped
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.user_repository import UserRepository
from app.services.notification_service import NotificationService
from app.services.price_check_service import PriceCheckService

logger = structlog.get_logger(__name__)


async def run_monitor_check(ctx: dict[str, Any], monitor_id: int) -> None:
    settings = ctx["settings"]
    redis = ctx["redis"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        monitor = await MonitorRepository(session).get(monitor_id)
        if monitor is None:
            logger.info("Monitor check skipped: monitor missing", monitor_id=monitor_id)
            return
        if monitor.status != MonitorStatus.ACTIVE:
            logger.info(
                "Monitor check skipped: monitor is not active",
                monitor_id=monitor_id,
                status=monitor.status,
            )
            return
        lock_key = _price_check_lock_key(monitor.url)

    async with acquire_redis_lock(
        redis,
        key=lock_key,
        ttl_seconds=settings.check_lock_ttl_seconds,
    ) as lock:
        if lock is None:
            async with session_factory() as session:
                await MonitorRepository(session).reschedule_after(
                    monitor_id,
                    settings.check_lock_retry_delay_seconds,
                )
            logger.info(
                "Monitor check skipped: URL lock is already held",
                monitor_id=monitor_id,
                lock_key=lock_key,
            )
            return

        try:
            async with session_factory() as session:
                service = PriceCheckService(
                    monitor_repository=MonitorRepository(session),
                    price_check_repository=PriceCheckRepository(session),
                    product_repository=ProductRepository(session),
                    notification_repository=NotificationRepository(session),
                    user_repository=UserRepository(session),
                    product_provider=ctx["product_provider"],
                    notification_dedupe_window_seconds=(
                        settings.notification_dedupe_window_seconds
                    ),
                )
                result = await service.run_check_with_result(monitor_id)

            for notification_id in result.notification_ids:
                await redis.enqueue_job(
                    "send_notification",
                    notification_id,
                    _job_id=f"send_notification:{notification_id}",
                )

            logger.info(
                "Monitor check completed",
                monitor_id=monitor_id,
                check_id=result.check.id,
                notification_ids=result.notification_ids,
            )
        except Exception as exc:
            if _is_final_try(ctx, settings.check_max_retries):
                await _dead_letter(
                    redis,
                    "dead:price_checks",
                    {
                        "job": "run_monitor_check",
                        "monitor_id": monitor_id,
                        "error": exc.__class__.__name__,
                        "message": str(exc),
                        "job_try": ctx.get("job_try"),
                    },
                    settings.dead_letter_max_items,
                )
                await _mark_monitor_error(ctx, monitor_id, exc)
            logger.exception("Monitor check failed", monitor_id=monitor_id)
            raise


async def run_due_monitor_checks(ctx: dict[str, Any]) -> None:
    settings = ctx["settings"]
    redis = ctx["redis"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        repository = MonitorRepository(session)
        monitors = await repository.claim_due(
            settings.check_batch_size,
            settings.check_lock_ttl_seconds,
        )

    for monitor in monitors:
        job = await redis.enqueue_job(
            "run_monitor_check",
            monitor.id,
            _job_id=f"run_monitor_check:{monitor.id}:{int(monitor.next_check_at.timestamp())}",
        )
        if job is None:
            logger.info("Due monitor already enqueued", monitor_id=monitor.id)

    logger.info("Due monitors scheduled", count=len(monitors))


async def send_notification(ctx: dict[str, Any], notification_id: int) -> None:
    settings = ctx["settings"]
    redis = ctx["redis"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        repository = NotificationRepository(session)
        notification = await repository.get_for_update(notification_id)
        if notification is None:
            logger.info("Notification skipped: missing", notification_id=notification_id)
            return
        if notification.status == NotificationStatus.SENT:
            logger.info("Notification skipped: already sent", notification_id=notification_id)
            return
        if notification.status not in {
            NotificationStatus.PENDING,
            NotificationStatus.FAILED,
        }:
            logger.info(
                "Notification skipped: status is not deliverable",
                notification_id=notification_id,
                status=notification.status,
            )
            return
        await repository.mark_processing(notification)

        service = NotificationService(providers=ctx.get("notification_providers", {}))
        try:
            await service.send(notification.channel, notification.payload)
        except NotificationSkipped as exc:
            await repository.mark_skipped(
                notification,
                error_code=exc.error_code,
                error_message=str(exc),
            )
            observe_notification_send(
                status=NotificationStatus.SKIPPED.value,
                channel=notification.channel,
                error_code=exc.error_code,
            )
            logger.info(
                "Notification delivery skipped",
                notification_id=notification_id,
                channel=notification.channel,
                error_code=exc.error_code,
            )
            return
        except NotificationDeliveryError as exc:
            await repository.mark_failed(
                notification,
                error_code=exc.error_code,
                error_message=str(exc),
            )
            observe_notification_send(
                status=NotificationStatus.FAILED.value,
                channel=notification.channel,
                error_code=exc.error_code,
            )
            if _is_final_try(ctx, settings.notification_max_retries):
                await _dead_letter(
                    redis,
                    "dead:notifications",
                    {
                        "job": "send_notification",
                        "notification_id": notification_id,
                        "channel": notification.channel,
                        "error": exc.__class__.__name__,
                        "error_code": exc.error_code,
                        "message": str(exc),
                        "job_try": ctx.get("job_try"),
                    },
                    settings.dead_letter_max_items,
                )
            logger.exception(
                "Notification delivery failed",
                notification_id=notification_id,
                channel=notification.channel,
                error_code=exc.error_code,
            )
            raise Retry(defer=_notification_retry_delay(ctx, settings)) from exc
        except Exception as exc:
            await repository.mark_failed(
                notification,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            observe_notification_send(
                status=NotificationStatus.FAILED.value,
                channel=notification.channel,
                error_code=exc.__class__.__name__,
            )
            if _is_final_try(ctx, settings.notification_max_retries):
                await _dead_letter(
                    redis,
                    "dead:notifications",
                    {
                        "job": "send_notification",
                        "notification_id": notification_id,
                        "channel": notification.channel,
                        "error": exc.__class__.__name__,
                        "message": str(exc),
                        "job_try": ctx.get("job_try"),
                    },
                    settings.dead_letter_max_items,
                )
            logger.exception("Notification delivery failed", notification_id=notification_id)
            raise Retry(defer=_notification_retry_delay(ctx, settings)) from exc

        await repository.mark_sent(notification)
        observe_notification_send(
            status=NotificationStatus.SENT.value,
            channel=notification.channel,
        )
        logger.info("Notification sent", notification_id=notification_id)


def _price_check_lock_key(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"lock:price_check:url:{digest}"


async def _dead_letter(redis, key: str, payload: dict[str, Any], max_items: int) -> None:
    await redis.lpush(key, json.dumps(payload, sort_keys=True, default=str))
    await redis.ltrim(key, 0, max_items - 1)


def _is_final_try(ctx: dict[str, Any], max_tries: int) -> bool:
    return int(ctx.get("job_try") or 1) >= max_tries


def _notification_retry_delay(ctx: dict[str, Any], settings) -> int:
    job_try = int(ctx.get("job_try") or 1)
    delay = settings.notification_retry_base_delay_seconds * (2 ** max(job_try - 1, 0))
    return min(delay, settings.notification_retry_max_delay_seconds)


async def _mark_monitor_error(ctx: dict[str, Any], monitor_id: int, exc: Exception) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        monitor = await MonitorRepository(session).get_for_update(monitor_id)
        if monitor is None:
            return
        monitor.status = MonitorStatus.ERROR
        monitor.error_code = exc.__class__.__name__
        monitor.error_reason = str(exc)[:255]
        monitor.next_check_at = None
        await session.commit()

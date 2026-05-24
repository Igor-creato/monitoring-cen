from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

import structlog

from app.common.clock import utc_now
from app.domain.enums import CheckStatus, MonitorStatus, NotificationStatus, NotificationType
from app.infra.db.models.price_check import PriceCheckModel
from app.infra.metrics import observe_check, observe_parser_error
from app.product_fetching.base import ProductDataProvider
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True, slots=True)
class PriceCheckRunResult:
    check: PriceCheckModel
    notification_ids: tuple[int, ...] = ()


logger = structlog.get_logger(__name__)


class PriceCheckService:
    def __init__(
        self,
        monitor_repository: MonitorRepository,
        price_check_repository: PriceCheckRepository,
        product_repository: ProductRepository | None = None,
        notification_repository: NotificationRepository | None = None,
        user_repository: UserRepository | None = None,
        product_provider: ProductDataProvider | None = None,
        notification_dedupe_window_seconds: int = 86_400,
    ):
        self.monitor_repository = monitor_repository
        self.price_check_repository = price_check_repository
        self.product_repository = product_repository
        self.notification_repository = notification_repository
        self.user_repository = user_repository
        self.product_provider = product_provider
        self.notification_dedupe_window_seconds = notification_dedupe_window_seconds

    async def run_check(self, monitor_id: int) -> PriceCheckModel:
        return (await self.run_check_with_result(monitor_id)).check

    async def run_check_with_result(self, monitor_id: int) -> PriceCheckRunResult:
        started_at = perf_counter()
        metric_marketplace = "unknown"
        metric_status = "failed"
        metric_error_code: str | None = None

        if self.product_provider is None or self.product_repository is None:
            result = await self._create_unconfigured_failure(monitor_id)
            observe_check(
                status=result.check.status.value,
                marketplace=metric_marketplace,
                error_code=result.check.error_code,
                duration_seconds=perf_counter() - started_at,
            )
            return result

        try:
            monitor = await self.monitor_repository.get_or_raise(monitor_id)
            metric_marketplace = str(monitor.marketplace.value)
            snapshot = await self.product_provider.fetch_product(monitor.url)
            metric_marketplace = str(snapshot.marketplace.value)
            source = await self.product_repository.get_or_create_source(
                original_url=monitor.url,
                normalized_url=snapshot.normalized_url,
                snapshot=snapshot,
            )

            monitor = await self.monitor_repository.get_for_update(monitor_id)
            if monitor is None:
                raise RuntimeError(f"Monitor {monitor_id} disappeared during price check")
            if monitor.status != MonitorStatus.ACTIVE:
                await self.monitor_repository.session.rollback()
                result = PriceCheckRunResult(
                    check=await self.price_check_repository.create_failure(
                        monitor_id=monitor_id,
                        error_code="monitor_not_active",
                        error_message=f"Monitor is {monitor.status}",
                    ),
                )
                metric_status = result.check.status.value
                metric_error_code = result.check.error_code
                logger.info(
                    "price_check.business_error",
                    error_kind="business",
                    monitor_id=monitor_id,
                    error_code=result.check.error_code,
                )
                return result

            now = utc_now()
            previous_price = monitor.last_price
            previous_currency = source.currency
            currency_changed = (
                previous_currency is not None
                and snapshot.currency is not None
                and previous_currency != snapshot.currency
            )
            check_status = CheckStatus.FAILED if currency_changed else None

            check = await self.price_check_repository.add_from_snapshot(
                monitor_id=monitor.id,
                product_source_id=source.id,
                snapshot=snapshot,
                status=check_status,
            )
            if currency_changed:
                check.error_code = "currency_changed"
                check.error_message = (
                    f"Currency changed from {previous_currency} to {snapshot.currency}; "
                    "target price was not evaluated"
                )
            elif snapshot.success and snapshot.current_price is None:
                check.error_code = "price_not_found"
                check.error_message = "Product snapshot did not contain current price"

            monitor.product_source_id = source.id
            monitor.marketplace = snapshot.marketplace
            monitor.last_checked_at = now
            monitor.next_check_at = now + timedelta(seconds=monitor.check_interval_seconds)

            notification_ids: list[int] = []
            if snapshot.success and snapshot.current_price is not None and not currency_changed:
                await self.product_repository.apply_success_snapshot(source, snapshot)
                monitor.last_price = snapshot.current_price
                monitor.error_code = None
                monitor.error_reason = None
                notification_ids.extend(
                    await self._create_target_notifications(
                        monitor=monitor,
                        check=check,
                        previous_price=previous_price,
                        current_price=snapshot.current_price,
                        currency=snapshot.currency,
                    )
                )
            else:
                await self.product_repository.apply_failure_snapshot(source, snapshot)
                parser_error_code = check.error_code or snapshot.error_code
                if (
                    parser_error_code is not None
                    and parser_error_code != "unsupported_product_url"
                    and not currency_changed
                ):
                    retryable = _is_retryable_parser_error(parser_error_code)
                    parser_error = await self.product_repository.record_parser_error(
                        source=source,
                        monitor_id=monitor.id,
                        snapshot=snapshot,
                        error_code=parser_error_code,
                        error_message=check.error_message or snapshot.error_message,
                        retryable=retryable,
                    )
                    observe_parser_error(
                        marketplace=snapshot.marketplace.value,
                        error_code=parser_error_code,
                        retryable=retryable,
                    )
                    logger.warning(
                        "parser.error",
                        error_kind="technical",
                        error_category="external_site",
                        monitor_id=monitor.id,
                        product_source_id=source.id,
                        parser_error_id=parser_error.id,
                        marketplace=snapshot.marketplace.value,
                        error_code=parser_error_code,
                        retryable=retryable,
                    )
                if currency_changed:
                    source.last_error_code = check.error_code
                    source.last_error_message = check.error_message
                monitor.error_code = check.error_code or snapshot.error_code
                monitor.error_reason = check.error_message or snapshot.error_message
                if snapshot.error_code == "unsupported_product_url":
                    monitor.status = MonitorStatus.UNSUPPORTED
                    monitor.next_check_at = None

            await self.monitor_repository.session.commit()
            result = PriceCheckRunResult(check=check, notification_ids=tuple(notification_ids))
            metric_status = result.check.status.value
            metric_error_code = result.check.error_code
            logger.info(
                "price_check.completed",
                monitor_id=monitor_id,
                check_id=check.id,
                status=check.status.value,
                marketplace=metric_marketplace,
                error_code=check.error_code,
                notification_count=len(notification_ids),
            )
            return result
        except Exception as exc:
            metric_error_code = exc.__class__.__name__
            logger.exception(
                "price_check.technical_error",
                error_kind="technical",
                monitor_id=monitor_id,
                error_code=metric_error_code,
            )
            raise
        finally:
            observe_check(
                status=metric_status,
                marketplace=metric_marketplace,
                error_code=metric_error_code,
                duration_seconds=perf_counter() - started_at,
            )

    async def _create_unconfigured_failure(self, monitor_id: int) -> PriceCheckRunResult:
        monitor = await self.monitor_repository.get_or_raise(monitor_id)
        check = await self.price_check_repository.create_failure(
            monitor_id=monitor.id,
            error_code="product_provider_not_configured",
            error_message="Product provider is not configured for this process",
        )
        return PriceCheckRunResult(check=check)

    async def _create_target_notifications(
        self,
        *,
        monitor,
        check: PriceCheckModel,
        previous_price: Decimal | None,
        current_price: Decimal,
        currency: str | None,
    ) -> list[int]:
        if self.notification_repository is None:
            return []
        if not self.should_notify_target(monitor.target_price, current_price):
            return []
        if monitor.notification_channel is None:
            return []

        recipient_email = await self._get_recipient_email(monitor.user_id)
        payload = {
            "notification_type": NotificationType.TARGET_REACHED.value,
            "monitor_id": monitor.id,
            "price_check_id": check.id,
            "url": monitor.url,
            "title": check.title,
            "target_price": str(monitor.target_price),
            "current_price": str(current_price),
            "previous_price": str(previous_price) if previous_price is not None else None,
            "currency": currency,
            "recipient_email": recipient_email,
        }

        notification_type = NotificationType.TARGET_REACHED
        dedupe_group_key = self.notification_repository.build_dedupe_group_key(
            notification_type=notification_type,
            monitor_id=monitor.id,
            channel=monitor.notification_channel,
            semantic_payload={
                "target_price": str(monitor.target_price),
                "current_price": str(current_price),
                "currency": currency,
                "url": monitor.url,
            },
        )
        now = utc_now()
        duplicate = await self.notification_repository.find_recent_by_dedupe_group(
            monitor_id=monitor.id,
            channel=monitor.notification_channel,
            notification_type=notification_type,
            dedupe_group_key=dedupe_group_key,
            since=now - timedelta(seconds=self.notification_dedupe_window_seconds),
        )
        if duplicate is not None:
            await self.notification_repository.create_history(
                monitor_id=monitor.id,
                user_id=monitor.user_id,
                product_source_id=monitor.product_source_id,
                price_check_id=check.id,
                channel=monitor.notification_channel,
                notification_type=notification_type,
                dedupe_key=f"{dedupe_group_key}:duplicated:{check.id or uuid4().hex}",
                status=NotificationStatus.DUPLICATED,
                payload={
                    **payload,
                    "duplicated_of_notification_id": duplicate.id,
                },
                error_code="duplicate_notification",
                error_message=(
                    "Same notification was already created inside the dedupe window"
                ),
            )
            return []

        notification = await self.notification_repository.create_history(
            monitor_id=monitor.id,
            user_id=monitor.user_id,
            product_source_id=monitor.product_source_id,
            price_check_id=check.id,
            channel=monitor.notification_channel,
            notification_type=notification_type,
            dedupe_key=f"{dedupe_group_key}:alert:{check.id or uuid4().hex}",
            status=NotificationStatus.PENDING,
            payload=payload,
        )
        monitor.last_notified_at = now
        return [notification.id]

    async def _get_recipient_email(self, user_id: int | None) -> str | None:
        if user_id is None or self.user_repository is None:
            return None
        user = await self.user_repository.get(user_id)
        return user.email if user is not None else None

    def should_notify_target(
        self,
        target_price: Decimal | None,
        current_price: Decimal,
    ) -> bool:
        return target_price is not None and current_price <= target_price


def _is_retryable_parser_error(error_code: str) -> bool:
    return error_code in {
        "provider_request_error",
        "provider_timeout",
        "provider_rate_limited",
        "network_error",
        "timeout",
    }

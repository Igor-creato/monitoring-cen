from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from app.common.clock import utc_now
from app.domain.enums import CheckStatus, MonitorStatus, NotificationType
from app.infra.db.models.price_check import PriceCheckModel
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.repositories.product_repository import ProductRepository
from app.product_fetching.base import ProductDataProvider


@dataclass(frozen=True, slots=True)
class PriceCheckRunResult:
    check: PriceCheckModel
    notification_ids: tuple[int, ...] = ()


class PriceCheckService:
    def __init__(
        self,
        monitor_repository: MonitorRepository,
        price_check_repository: PriceCheckRepository,
        product_repository: ProductRepository | None = None,
        notification_repository: NotificationRepository | None = None,
        product_provider: ProductDataProvider | None = None,
    ):
        self.monitor_repository = monitor_repository
        self.price_check_repository = price_check_repository
        self.product_repository = product_repository
        self.notification_repository = notification_repository
        self.product_provider = product_provider

    async def run_check(self, monitor_id: int) -> PriceCheckModel:
        return (await self.run_check_with_result(monitor_id)).check

    async def run_check_with_result(self, monitor_id: int) -> PriceCheckRunResult:
        if self.product_provider is None or self.product_repository is None:
            return await self._create_unconfigured_failure(monitor_id)

        monitor = await self.monitor_repository.get_or_raise(monitor_id)
        snapshot = await self.product_provider.fetch_product(monitor.url)
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
            return PriceCheckRunResult(
                check=await self.price_check_repository.create_failure(
                    monitor_id=monitor_id,
                    error_code="monitor_not_active",
                    error_message=f"Monitor is {monitor.status}",
                ),
            )

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
            if currency_changed:
                source.last_error_code = check.error_code
                source.last_error_message = check.error_message
            monitor.error_code = check.error_code or snapshot.error_code
            monitor.error_reason = check.error_message or snapshot.error_message
            if snapshot.error_code == "unsupported_product_url":
                monitor.status = MonitorStatus.UNSUPPORTED
                monitor.next_check_at = None

        await self.monitor_repository.session.commit()
        return PriceCheckRunResult(check=check, notification_ids=tuple(notification_ids))

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

        payload = {
            "monitor_id": monitor.id,
            "price_check_id": check.id,
            "url": monitor.url,
            "target_price": str(monitor.target_price),
            "current_price": str(current_price),
            "previous_price": str(previous_price) if previous_price is not None else None,
            "currency": currency,
        }
        notification, created = await self.notification_repository.create_pending_once(
            monitor_id=monitor.id,
            user_id=monitor.user_id,
            product_source_id=monitor.product_source_id,
            price_check_id=check.id,
            channel=monitor.notification_channel,
            notification_type=NotificationType.TARGET_REACHED,
            dedupe_key=f"target_reached:{monitor.target_price}:{currency or 'unknown'}",
            payload=payload,
        )
        if not created:
            return []
        monitor.last_notified_at = utc_now()
        return [notification.id]

    def should_notify_target(
        self,
        target_price: Decimal | None,
        current_price: Decimal,
    ) -> bool:
        return target_price is not None and current_price <= target_price

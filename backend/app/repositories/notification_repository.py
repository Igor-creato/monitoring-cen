import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clock import utc_now
from app.domain.enums import NotificationStatus, NotificationType
from app.infra.db.models.notification import NotificationModel


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_pending(
        self,
        monitor_id: int,
        channel: str,
        payload: dict,
        notification_type: NotificationType = NotificationType.PRICE_CHANGED,
        dedupe_key: str | None = None,
        user_id: int | None = None,
        product_source_id: int | None = None,
        price_check_id: int | None = None,
    ) -> NotificationModel:
        dedupe_key = dedupe_key or self.build_dedupe_key(notification_type, payload)

        notification = NotificationModel(
            user_id=user_id,
            monitor_id=monitor_id,
            product_source_id=product_source_id,
            price_check_id=price_check_id,
            notification_type=notification_type,
            status=NotificationStatus.PENDING,
            channel=channel,
            dedupe_key=dedupe_key,
            payload=payload,
            scheduled_at=utc_now(),
        )
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def create_pending_once(
        self,
        *,
        monitor_id: int,
        channel: str,
        payload: dict,
        notification_type: NotificationType,
        dedupe_key: str,
        user_id: int | None,
        product_source_id: int | None,
        price_check_id: int | None,
    ) -> tuple[NotificationModel, bool]:
        existing = await self.get_by_dedupe(
            monitor_id=monitor_id,
            channel=channel,
            notification_type=notification_type,
            dedupe_key=dedupe_key,
        )
        if existing is not None:
            return existing, False

        notification = NotificationModel(
            user_id=user_id,
            monitor_id=monitor_id,
            product_source_id=product_source_id,
            price_check_id=price_check_id,
            notification_type=notification_type,
            status=NotificationStatus.PENDING,
            channel=channel,
            dedupe_key=dedupe_key,
            payload=payload,
            scheduled_at=utc_now(),
        )
        self.session.add(notification)
        await self.session.flush()
        return notification, True

    async def get(self, notification_id: int) -> NotificationModel | None:
        result = await self.session.execute(
            select(NotificationModel).where(NotificationModel.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, notification_id: int) -> NotificationModel | None:
        result = await self.session.execute(
            select(NotificationModel)
            .where(NotificationModel.id == notification_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_dedupe(
        self,
        *,
        monitor_id: int,
        channel: str,
        notification_type: NotificationType,
        dedupe_key: str,
    ) -> NotificationModel | None:
        result = await self.session.execute(
            select(NotificationModel)
            .where(NotificationModel.monitor_id == monitor_id)
            .where(NotificationModel.notification_type == notification_type)
            .where(NotificationModel.channel == channel)
            .where(NotificationModel.dedupe_key == dedupe_key)
        )
        return result.scalar_one_or_none()

    async def mark_processing(self, notification: NotificationModel) -> None:
        notification.status = NotificationStatus.PROCESSING
        await self.session.commit()

    async def mark_sent(self, notification: NotificationModel) -> None:
        now = utc_now()
        notification.status = NotificationStatus.SENT
        notification.sent_at = now
        notification.error_code = None
        notification.error_message = None
        await self.session.commit()

    async def mark_failed(
        self,
        notification: NotificationModel,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        now = utc_now()
        notification.status = NotificationStatus.FAILED
        notification.failed_at = now
        notification.error_code = error_code
        notification.error_message = error_message
        await self.session.commit()

    @staticmethod
    def build_dedupe_key(notification_type: NotificationType, payload: dict) -> str:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        return f"{notification_type.value}:{digest}"

import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession

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
    ) -> NotificationModel:
        if dedupe_key is None:
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
            digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            dedupe_key = f"{notification_type.value}:{digest}"

        notification = NotificationModel(
            monitor_id=monitor_id,
            notification_type=notification_type,
            status=NotificationStatus.PENDING,
            channel=channel,
            dedupe_key=dedupe_key,
            payload=payload,
        )
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

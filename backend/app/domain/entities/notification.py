from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import NotificationStatus, NotificationType


@dataclass(slots=True)
class Notification:
    id: int | None
    user_id: int | None
    monitor_id: int
    notification_type: NotificationType
    status: NotificationStatus
    channel: str
    dedupe_key: str
    payload: dict
    created_at: datetime
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    failed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    def can_be_delivered(self) -> bool:
        return self.status in {
            NotificationStatus.PENDING,
            NotificationStatus.FAILED,
        }

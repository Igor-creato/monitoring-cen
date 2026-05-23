from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import NotificationStatus


@dataclass(slots=True)
class Notification:
    id: int | None
    monitor_id: int
    status: NotificationStatus
    channel: str
    payload: dict
    created_at: datetime
    sent_at: datetime | None = None
    error_message: str | None = None

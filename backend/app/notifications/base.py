from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    subject: str
    text: str
    recipient: str | None
    html: str | None = None
    metadata: dict | None = None


class NotificationProvider(Protocol):
    channel: str

    async def send(self, message: NotificationMessage) -> None: ...


class NotificationSkipped(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class NotificationDeliveryError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


NotificationSender = NotificationProvider

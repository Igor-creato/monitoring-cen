from typing import Protocol


class NotificationSender(Protocol):
    channel: str

    async def send(self, payload: dict) -> None: ...

from app.notifications.base import NotificationSender


class NotificationService:
    def __init__(self, senders: dict[str, NotificationSender]):
        self.senders = senders

    async def send(self, channel: str, payload: dict) -> None:
        sender = self.senders[channel]
        await sender.send(payload)

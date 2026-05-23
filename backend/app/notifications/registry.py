from app.notifications.base import NotificationSender


class NotificationSenderRegistry:
    def __init__(self, senders: list[NotificationSender]):
        self._senders = {sender.channel: sender for sender in senders}

    def get(self, channel: str) -> NotificationSender:
        return self._senders[channel]

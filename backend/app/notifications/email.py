from app.notifications.base import NotificationSender


class EmailNotificationSender(NotificationSender):
    channel = "email"

    async def send(self, payload: dict) -> None:
        raise NotImplementedError("Email notifications are not implemented yet")

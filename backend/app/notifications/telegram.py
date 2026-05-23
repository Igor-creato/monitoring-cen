from app.notifications.base import NotificationSender


class TelegramNotificationSender(NotificationSender):
    channel = "telegram"

    def __init__(self, bot_token: str):
        self.bot_token = bot_token

    async def send(self, payload: dict) -> None:
        raise NotImplementedError("Telegram notifications are not implemented yet")

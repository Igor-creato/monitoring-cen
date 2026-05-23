import httpx

from app.notifications.base import NotificationSender


class WebhookNotificationSender(NotificationSender):
    channel = "webhook"

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    async def send(self, payload: dict) -> None:
        raise NotImplementedError("Webhook notifications are not implemented yet")

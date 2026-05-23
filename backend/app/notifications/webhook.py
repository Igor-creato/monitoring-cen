import httpx

from app.notifications.base import NotificationMessage, NotificationProvider, NotificationSkipped


class WebhookNotificationSender(NotificationProvider):
    channel = "webhook"

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    async def send(self, message: NotificationMessage) -> None:
        raise NotificationSkipped(
            "webhook_provider_not_configured",
            "Webhook notifications are not implemented yet",
        )

from collections.abc import Mapping

from app.notifications.base import NotificationProvider, NotificationSkipped
from app.notifications.templates import render_notification


class NotificationService:
    def __init__(self, providers: Mapping[str, NotificationProvider]):
        self.providers = providers

    async def send(self, channel: str, payload: dict) -> None:
        provider = self.providers.get(channel)
        if provider is None:
            raise NotificationSkipped(
                "notification_channel_not_configured",
                f"Notification channel is not configured: {channel}",
            )

        message = render_notification(payload)
        await provider.send(message)

from collections.abc import Iterable

from app.infra.config import Settings
from app.notifications.base import NotificationProvider
from app.notifications.email import EmailProvider
from app.notifications.telegram import TelegramProvider


class NotificationProviderRegistry:
    def __init__(self, providers: Iterable[NotificationProvider]):
        self._providers = {provider.channel: provider for provider in providers}

    def get(self, channel: str) -> NotificationProvider | None:
        return self._providers.get(channel)

    def as_dict(self) -> dict[str, NotificationProvider]:
        return dict(self._providers)


def create_notification_providers(settings: Settings) -> NotificationProviderRegistry:
    return NotificationProviderRegistry(
        [
            EmailProvider(
                smtp_host=settings.email_smtp_host,
                smtp_port=settings.email_smtp_port,
                username=settings.email_smtp_user,
                password=settings.email_smtp_password,
                from_email=settings.email_smtp_from,
                use_tls=settings.email_smtp_use_tls,
            ),
            TelegramProvider(bot_token=settings.telegram_bot_token),
        ]
    )


NotificationSenderRegistry = NotificationProviderRegistry

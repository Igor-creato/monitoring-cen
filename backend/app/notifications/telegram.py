import structlog

from app.notifications.base import NotificationMessage, NotificationProvider, NotificationSkipped

logger = structlog.get_logger(__name__)


class TelegramProvider(NotificationProvider):
    channel = "telegram"

    def __init__(self, bot_token: str | None):
        self.bot_token = bot_token

    async def send(self, message: NotificationMessage) -> None:
        if not self.bot_token:
            raise NotificationSkipped(
                "telegram_provider_not_configured",
                "Telegram provider is not configured",
            )

        chat_id = (message.metadata or {}).get("telegram_chat_id")
        if not chat_id:
            raise NotificationSkipped(
                "telegram_chat_id_missing",
                "Telegram chat id is missing",
            )

        logger.info(
            "Telegram notification stub skipped",
            chat_id=chat_id,
            subject=message.subject,
        )
        raise NotificationSkipped(
            "telegram_provider_stub",
            "Telegram provider is a stub for MVP and does not deliver messages yet",
        )


TelegramNotificationSender = TelegramProvider

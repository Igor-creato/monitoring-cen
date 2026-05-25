import structlog

from app.notifications.base import (
    NotificationDeliveryError,
    NotificationMessage,
    NotificationSkipped,
)
from app.notifications.email import EmailProvider

logger = structlog.get_logger(__name__)


class PasswordResetEmailSender:
    def __init__(self, provider: EmailProvider):
        self.provider = provider

    async def send(self, *, recipient: str, reset_url: str) -> None:
        message = NotificationMessage(
            subject="Сброс пароля",
            recipient=recipient,
            text=(
                "Вы запросили сброс пароля.\n\n"
                f"Чтобы задать новый пароль, откройте ссылку: {reset_url}\n\n"
                "Если вы не запрашивали сброс, просто проигнорируйте это письмо."
            ),
        )
        try:
            await self.provider.send(message)
        except (NotificationSkipped, NotificationDeliveryError) as exc:
            logger.warning(
                "password_reset.email_skipped",
                error_code=exc.error_code,
            )

import asyncio
import smtplib
from email.message import EmailMessage

from app.notifications.base import (
    NotificationDeliveryError,
    NotificationMessage,
    NotificationProvider,
    NotificationSkipped,
)


class EmailProvider(NotificationProvider):
    channel = "email"

    def __init__(
        self,
        *,
        smtp_host: str | None,
        smtp_port: int | None,
        username: str | None,
        password: str | None,
        from_email: str | None,
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email or username
        self.use_tls = use_tls

    async def send(self, message: NotificationMessage) -> None:
        if not self.smtp_host or not self.smtp_port or not self.from_email:
            raise NotificationSkipped(
                "email_provider_not_configured",
                "Email provider is not configured",
            )
        if not message.recipient:
            raise NotificationSkipped(
                "email_recipient_missing",
                "Email notification recipient is missing",
            )

        email = EmailMessage()
        email["From"] = self.from_email
        email["To"] = message.recipient
        email["Subject"] = message.subject
        email.set_content(message.text)
        if message.html:
            email.add_alternative(message.html, subtype="html")

        try:
            await asyncio.to_thread(self._send_sync, email)
        except smtplib.SMTPException as exc:
            raise NotificationDeliveryError(exc.__class__.__name__, str(exc)) from exc
        except OSError as exc:
            raise NotificationDeliveryError(exc.__class__.__name__, str(exc)) from exc

    def _send_sync(self, email: EmailMessage) -> None:
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(email)


EmailNotificationSender = EmailProvider

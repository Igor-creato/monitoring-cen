import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Protocol

from app.api.v1.schemas.auth import LoginRequest, RegisterRequest
from app.common.clock import utc_now
from app.domain.enums import UserRole, UserStatus
from app.domain.exceptions import AuthenticationError
from app.infra.config import Settings
from app.infra.db.models.user import UserModel
from app.infra.security import create_access_token, hash_password, verify_password
from app.repositories.password_reset_token_repository import PasswordResetTokenRepository
from app.repositories.user_repository import UserRepository


class PasswordResetSender(Protocol):
    async def send(self, *, recipient: str, reset_url: str) -> None: ...


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        settings: Settings,
        *,
        password_reset_tokens: PasswordResetTokenRepository | None = None,
        password_reset_sender: PasswordResetSender | None = None,
    ):
        self.user_repository = user_repository
        self.settings = settings
        self.password_reset_tokens = password_reset_tokens
        self.password_reset_sender = password_reset_sender

    async def register(self, payload: RegisterRequest) -> tuple[UserModel, str, datetime]:
        user = await self.user_repository.create(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password, self.settings),
            role=self._role_for_email(payload.email),
        )
        token, expires_at = create_access_token(user.id, self.settings)
        return user, token, expires_at

    async def login(self, payload: LoginRequest) -> tuple[UserModel, str, datetime]:
        user = await self.user_repository.get_by_email(payload.email.lower())
        if (
            user is None
            or user.status != UserStatus.ACTIVE
            or not verify_password(payload.password, user.password_hash)
        ):
            raise AuthenticationError("Invalid email or password")

        if self._role_for_email(user.email) == UserRole.ADMIN and user.role != UserRole.ADMIN:
            user.role = UserRole.ADMIN
            await self.user_repository.session.commit()
            await self.user_repository.session.refresh(user)

        token, expires_at = create_access_token(user.id, self.settings)
        return user, token, expires_at

    async def request_password_reset(self, email: str, base_url: str | None = None) -> str | None:
        if self.password_reset_tokens is None or self.password_reset_sender is None:
            return None

        user = await self.user_repository.get_by_email(email.strip().lower())
        if user is None or user.status != UserStatus.ACTIVE:
            return None

        reset_base_url = (self.settings.app_base_url or base_url or "").rstrip("/")
        if not reset_base_url:
            return None

        raw_token = secrets.token_urlsafe(32)
        token_hash = _password_reset_token_hash(raw_token)
        expires_at = utc_now() + timedelta(
            minutes=self.settings.password_reset_token_expire_minutes
        )

        await self.password_reset_tokens.invalidate_active_for_user(user.id)
        await self.password_reset_tokens.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self.user_repository.session.commit()

        await self.password_reset_sender.send(
            recipient=user.email,
            reset_url=f"{reset_base_url}/reset-password?token={raw_token}",
        )
        return raw_token

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        if self.password_reset_tokens is None:
            raise AuthenticationError("Invalid or expired password reset token")

        now = utc_now()
        reset_token = await self.password_reset_tokens.get_active_by_hash(
            _password_reset_token_hash(token),
            now,
        )
        if reset_token is None:
            raise AuthenticationError("Invalid or expired password reset token")

        user = await self.user_repository.get(reset_token.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise AuthenticationError("Invalid or expired password reset token")

        user.password_hash = hash_password(new_password, self.settings)
        await self.password_reset_tokens.mark_used(reset_token, now)
        await self.user_repository.session.commit()

    def _role_for_email(self, email: str) -> UserRole:
        admin_emails = {
            item.strip().lower()
            for item in self.settings.admin_emails.split(",")
            if item.strip()
        }
        return UserRole.ADMIN if email.strip().lower() in admin_emails else UserRole.USER


def _password_reset_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

from datetime import datetime

from app.api.v1.schemas.auth import LoginRequest, RegisterRequest
from app.domain.enums import UserRole, UserStatus
from app.domain.exceptions import AuthenticationError
from app.infra.config import Settings
from app.infra.db.models.user import UserModel
from app.infra.security import create_access_token, hash_password, verify_password
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, user_repository: UserRepository, settings: Settings):
        self.user_repository = user_repository
        self.settings = settings

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

    def _role_for_email(self, email: str) -> UserRole:
        admin_emails = {
            item.strip().lower()
            for item in self.settings.admin_emails.split(",")
            if item.strip()
        }
        return UserRole.ADMIN if email.strip().lower() in admin_emails else UserRole.USER

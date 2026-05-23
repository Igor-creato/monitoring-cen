from datetime import datetime

from app.api.v1.schemas.auth import LoginRequest, RegisterRequest
from app.domain.enums import UserStatus
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

        token, expires_at = create_access_token(user.id, self.settings)
        return user, token, expires_at

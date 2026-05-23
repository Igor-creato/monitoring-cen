from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import UserStatus
from app.domain.exceptions import ConflictError, EntityNotFoundError
from app.infra.db.models.user import UserModel


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, email: str, password_hash: str) -> UserModel:
        user = UserModel(email=email, password_hash=password_hash)
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("User with this email already exists") from exc

        await self.session.refresh(user)
        return user

    async def get(self, user_id: int) -> UserModel | None:
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_active_or_raise(self, user_id: int) -> UserModel:
        user = await self.get(user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise EntityNotFoundError(f"User {user_id} was not found")
        return user

    async def get_by_email(self, email: str) -> UserModel | None:
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        return result.scalar_one_or_none()

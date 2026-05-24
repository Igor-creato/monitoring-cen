from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import UserRole, UserStatus
from app.domain.exceptions import ConflictError, EntityNotFoundError
from app.infra.db.models.user import UserModel


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.USER,
    ) -> UserModel:
        user = UserModel(email=email, password_hash=password_hash, role=role)
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

    async def list_users(
        self,
        limit: int,
        offset: int,
        query: str | None = None,
        status: UserStatus | None = None,
        role: UserRole | None = None,
    ) -> tuple[int, list[UserModel]]:
        filters = []
        if query:
            filters.append(UserModel.email.ilike(f"%{query.lower()}%"))
        if status is not None:
            filters.append(UserModel.status == status)
        if role is not None:
            filters.append(UserModel.role == role)

        total_result = await self.session.execute(
            select(func.count()).select_from(UserModel).where(*filters)
        )
        rows_result = await self.session.execute(
            select(UserModel)
            .where(*filters)
            .order_by(UserModel.created_at.desc(), UserModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return total_result.scalar_one(), list(rows_result.scalars().all())

    async def count_admins(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(UserModel)
            .where(UserModel.role == UserRole.ADMIN)
            .where(UserModel.status == UserStatus.ACTIVE)
        )
        return result.scalar_one()

    async def update_user(
        self,
        user: UserModel,
        values: dict[str, object],
    ) -> UserModel:
        for field, value in values.items():
            setattr(user, field, value)
        await self.session.commit()
        await self.session.refresh(user)
        return user

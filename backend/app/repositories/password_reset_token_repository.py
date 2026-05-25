from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clock import utc_now
from app.infra.db.models.password_reset_token import PasswordResetTokenModel


class PasswordResetTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetTokenModel:
        token = PasswordResetTokenModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token)
        return token

    async def invalidate_active_for_user(self, user_id: int) -> None:
        await self.session.execute(
            update(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
            .where(PasswordResetTokenModel.used_at.is_(None))
            .values(used_at=utc_now())
        )

    async def get_active_by_hash(
        self,
        token_hash: str,
        now: datetime,
    ) -> PasswordResetTokenModel | None:
        result = await self.session.execute(
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.token_hash == token_hash)
            .where(PasswordResetTokenModel.used_at.is_(None))
            .where(PasswordResetTokenModel.expires_at > now)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: PasswordResetTokenModel, used_at: datetime) -> None:
        token.used_at = used_at

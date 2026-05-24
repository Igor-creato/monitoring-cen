from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models.service_setting import ServiceSettingModel


class ServiceSettingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> ServiceSettingModel | None:
        result = await self.session.execute(
            select(ServiceSettingModel).where(ServiceSettingModel.key == key)
        )
        return result.scalar_one_or_none()

    async def list_by_keys(self, keys: Iterable[str]) -> dict[str, ServiceSettingModel]:
        key_list = list(keys)
        if not key_list:
            return {}
        result = await self.session.execute(
            select(ServiceSettingModel).where(ServiceSettingModel.key.in_(key_list))
        )
        return {item.key: item for item in result.scalars().all()}

    async def upsert_plain(
        self,
        key: str,
        value: str,
        updated_by_user_id: int | None,
    ) -> ServiceSettingModel:
        setting = await self.get(key)
        if setting is None:
            setting = ServiceSettingModel(key=key)
            self.session.add(setting)
        setting.value_text = value
        setting.secret_encrypted = None
        setting.is_secret = False
        setting.updated_by_user_id = updated_by_user_id
        await self.session.commit()
        await self.session.refresh(setting)
        return setting

    async def upsert_secret(
        self,
        key: str,
        encrypted_value: str,
        updated_by_user_id: int | None,
    ) -> ServiceSettingModel:
        setting = await self.get(key)
        if setting is None:
            setting = ServiceSettingModel(key=key)
            self.session.add(setting)
        setting.value_text = None
        setting.secret_encrypted = encrypted_value
        setting.is_secret = True
        setting.updated_by_user_id = updated_by_user_id
        await self.session.commit()
        await self.session.refresh(setting)
        return setting

    async def delete(self, key: str) -> bool:
        setting = await self.get(key)
        if setting is None:
            return False
        await self.session.delete(setting)
        await self.session.commit()
        return True

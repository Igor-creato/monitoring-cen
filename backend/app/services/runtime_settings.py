from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.config import Settings
from app.infra.db.models.service_setting import ServiceSettingModel
from app.repositories.service_setting_repository import ServiceSettingRepository

SECRET_SETTING_KEYS = frozenset({"apify_api_token", "zyte_api_key", "internal_api_token"})
PLAIN_SETTING_KEYS = frozenset(
    {"product_fetch_provider", "apify_actor_id", "apify_base_url", "zyte_api_url"}
)
SERVICE_SETTING_KEYS = SECRET_SETTING_KEYS | PLAIN_SETTING_KEYS


class RuntimeSettingsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SettingStatus:
    key: str
    is_secret: bool
    source: str
    masked_value: str
    updated_at: datetime | None = None


class RuntimeSettingsService:
    def __init__(self, repository: ServiceSettingRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    async def list_statuses(self) -> list[SettingStatus]:
        db_values = await self.repository.list_by_keys(SERVICE_SETTING_KEYS)
        return [self._status_for(key, db_values.get(key)) for key in sorted(SERVICE_SETTING_KEYS)]

    async def set_plain(
        self,
        key: str,
        value: str,
        updated_by_user_id: int | None,
    ) -> ServiceSettingModel:
        if key not in PLAIN_SETTING_KEYS:
            raise RuntimeSettingsError(f"Unsupported plain setting '{key}'")
        value = value.strip()
        if not value:
            raise RuntimeSettingsError("Setting value cannot be empty")
        return await self.repository.upsert_plain(key, value, updated_by_user_id)

    async def set_secret(
        self,
        key: str,
        value: str,
        updated_by_user_id: int | None,
    ) -> ServiceSettingModel:
        if key not in SECRET_SETTING_KEYS:
            raise RuntimeSettingsError(f"Unsupported secret setting '{key}'")
        value = value.strip()
        if not value:
            raise RuntimeSettingsError("Secret value cannot be empty")
        encrypted = self._fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return await self.repository.upsert_secret(key, encrypted, updated_by_user_id)

    async def clear(self, key: str) -> bool:
        if key not in SERVICE_SETTING_KEYS:
            raise RuntimeSettingsError(f"Unsupported setting '{key}'")
        return await self.repository.delete(key)

    async def resolve_settings(self) -> Settings:
        overrides: dict[str, str] = {}
        db_values = await self.repository.list_by_keys(SERVICE_SETTING_KEYS)
        for key, setting in db_values.items():
            if key in SECRET_SETTING_KEYS and setting.secret_encrypted:
                overrides[key] = self.decrypt_secret(setting)
            elif key in PLAIN_SETTING_KEYS and setting.value_text:
                overrides[key] = setting.value_text
        return self.settings.model_copy(update=overrides)

    async def internal_api_token(self) -> str | None:
        setting = await self.repository.get("internal_api_token")
        if setting is not None and setting.secret_encrypted:
            return self.decrypt_secret(setting)
        return self.settings.internal_api_token

    def decrypt_secret(self, setting: ServiceSettingModel) -> str:
        if not setting.secret_encrypted:
            return ""
        try:
            return self._fernet().decrypt(setting.secret_encrypted.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeSettingsError(f"Cannot decrypt setting '{setting.key}'") from exc

    def _status_for(
        self,
        key: str,
        setting: ServiceSettingModel | None,
    ) -> SettingStatus:
        is_secret = key in SECRET_SETTING_KEYS
        env_value = getattr(self.settings, key)
        if setting is not None:
            value = setting.secret_encrypted if is_secret else setting.value_text
            if value:
                return SettingStatus(
                    key=key,
                    is_secret=is_secret,
                    source="db",
                    masked_value=_mask_value(self.decrypt_secret(setting) if is_secret else value),
                    updated_at=setting.updated_at,
                )
        if env_value:
            return SettingStatus(
                key=key,
                is_secret=is_secret,
                source="env",
                masked_value=_mask_value(str(env_value)),
            )
        return SettingStatus(key=key, is_secret=is_secret, source="missing", masked_value="")

    def _fernet(self) -> Fernet:
        if not self.settings.admin_secrets_key:
            raise RuntimeSettingsError("ADMIN_SECRETS_KEY is required for encrypted settings")
        try:
            return Fernet(self.settings.admin_secrets_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeSettingsError("ADMIN_SECRETS_KEY must be a valid Fernet key") from exc


async def resolve_runtime_settings(session: AsyncSession, settings: Settings) -> Settings:
    service = RuntimeSettingsService(ServiceSettingRepository(session), settings)
    return await service.resolve_settings()


async def resolve_internal_api_token(session: AsyncSession, settings: Settings) -> str | None:
    service = RuntimeSettingsService(ServiceSettingRepository(session), settings)
    return await service.internal_api_token()


def _mask_value(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"

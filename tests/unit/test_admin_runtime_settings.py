from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.api import deps
from app.domain.enums import UserRole, UserStatus
from app.domain.exceptions import AuthorizationError
from app.infra.config import Settings
from app.infra.db.models.service_setting import ServiceSettingModel
from app.infra.security import hash_password
from app.services.auth_service import AuthService
from app.services.runtime_settings import RuntimeSettingsError, RuntimeSettingsService


class FakeUserRepository:
    def __init__(self, user=None) -> None:
        self.created_role = None
        self.user = user
        self.committed = False
        self.refreshed = None

    async def create(self, *, email, password_hash, role):
        self.created_role = role
        return SimpleNamespace(id=1, email=email, role=role)

    async def get_by_email(self, email):
        return self.user

    @property
    def session(self):
        return self

    async def commit(self):
        self.committed = True

    async def refresh(self, user):
        self.refreshed = user


class FakeSettingsRepository:
    def __init__(self, values=None) -> None:
        self.values = values or {}
        self.saved = {}
        self.deleted = []

    async def get(self, key):
        return self.values.get(key)

    async def list_by_keys(self, keys):
        return {key: self.values[key] for key in keys if key in self.values}

    async def upsert_plain(self, key, value, updated_by_user_id):
        setting = ServiceSettingModel(
            key=key,
            value_text=value,
            is_secret=False,
            updated_by_user_id=updated_by_user_id,
        )
        self.saved[key] = setting
        self.values[key] = setting
        return setting

    async def upsert_secret(self, key, encrypted_value, updated_by_user_id):
        setting = ServiceSettingModel(
            key=key,
            secret_encrypted=encrypted_value,
            is_secret=True,
            updated_by_user_id=updated_by_user_id,
        )
        self.saved[key] = setting
        self.values[key] = setting
        return setting

    async def delete(self, key):
        self.deleted.append(key)
        return self.values.pop(key, None) is not None


@pytest.mark.asyncio
async def test_register_bootstraps_admin_from_env_email() -> None:
    settings = Settings(
        jwt_secret_key="test-secret",
        admin_emails="admin@example.com, other@example.com",
    )
    repository = FakeUserRepository()
    service = AuthService(repository, settings)  # type: ignore[arg-type]

    user, _token, _expires_at = await service.register(
        SimpleNamespace(email="Admin@Example.com", password="password123")
    )

    assert user.role == UserRole.ADMIN
    assert repository.created_role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_login_promotes_env_admin_user() -> None:
    settings = Settings(jwt_secret_key="test-secret", admin_emails="admin@example.com")
    user = SimpleNamespace(
        id=1,
        email="admin@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        password_hash=hash_password("password", settings),
    )
    repository = FakeUserRepository(user)
    service = AuthService(repository, settings)  # type: ignore[arg-type]

    logged_in, _token, _expires_at = await service.login(
        SimpleNamespace(email="admin@example.com", password="password")
    )

    assert logged_in.role == UserRole.ADMIN
    assert repository.committed is True
    assert repository.refreshed is user


@pytest.mark.asyncio
async def test_runtime_secret_is_encrypted_masked_and_resolved() -> None:
    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        jwt_secret_key="test-secret",
        admin_secrets_key=key,
        apify_api_token="env-token",
        product_fetch_provider="mock",
    )
    repository = FakeSettingsRepository()
    service = RuntimeSettingsService(repository, settings)  # type: ignore[arg-type]

    await service.set_secret("apify_api_token", "db-token-secret", 7)
    await service.set_plain("product_fetch_provider", "apify", 7)
    resolved = await service.resolve_settings()
    statuses = {item.key: item for item in await service.list_statuses()}

    encrypted = repository.saved["apify_api_token"].secret_encrypted
    assert encrypted is not None and "db-token-secret" not in encrypted
    assert resolved.apify_api_token == "db-token-secret"
    assert resolved.product_fetch_provider == "apify"
    assert statuses["apify_api_token"].source == "db"
    assert statuses["apify_api_token"].masked_value == "db-t...cret"


@pytest.mark.asyncio
async def test_secret_write_requires_admin_secret_key() -> None:
    service = RuntimeSettingsService(
        FakeSettingsRepository(),  # type: ignore[arg-type]
        Settings(jwt_secret_key="test-secret", admin_secrets_key=None),
    )

    with pytest.raises(RuntimeSettingsError, match="ADMIN_SECRETS_KEY"):
        await service.set_secret("internal_api_token", "secret", 1)


@pytest.mark.asyncio
async def test_internal_token_dependency_uses_resolved_token(monkeypatch) -> None:
    async def fake_resolve_internal_api_token(session, settings):
        return "db-token"

    monkeypatch.setattr(deps, "resolve_internal_api_token", fake_resolve_internal_api_token)

    await deps.require_internal_token(
        x_internal_token="db-token",
        session=object(),  # type: ignore[arg-type]
        settings=Settings(jwt_secret_key="test-secret", internal_api_token="env-token"),
    )
    with pytest.raises(AuthorizationError):
        await deps.require_internal_token(
            x_internal_token="env-token",
            session=object(),  # type: ignore[arg-type]
            settings=Settings(jwt_secret_key="test-secret", internal_api_token="env-token"),
        )

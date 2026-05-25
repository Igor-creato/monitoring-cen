from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.v1.schemas.auth import LoginRequest
from app.domain.enums import UserRole, UserStatus
from app.domain.exceptions import AuthenticationError
from app.infra.config import Settings
from app.infra.security import hash_password
from app.services.auth_service import AuthService


class FakeUserRepository:
    def __init__(self, user=None) -> None:
        self.user = user
        self.session = SimpleNamespace(commit=self.commit, refresh=self.refresh)
        self.commits = 0

    async def get_by_email(self, email):
        if self.user and self.user.email == email:
            return self.user
        return None

    async def get(self, user_id):
        if self.user and self.user.id == user_id:
            return self.user
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, user):
        return None


class FakePasswordResetTokenRepository:
    def __init__(self, token=None) -> None:
        self.token = token
        self.created = None
        self.invalidated_user_ids = []

    async def invalidate_active_for_user(self, user_id):
        self.invalidated_user_ids.append(user_id)
        if self.token:
            self.token.used_at = datetime.now(UTC)

    async def create(self, *, user_id, token_hash, expires_at):
        self.created = SimpleNamespace(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
        )
        self.token = self.created
        return self.created

    async def get_active_by_hash(self, token_hash, now):
        if (
            self.token
            and self.token.token_hash == token_hash
            and self.token.used_at is None
            and self.token.expires_at > now
        ):
            return self.token
        return None

    async def mark_used(self, token, used_at):
        token.used_at = used_at


class FakePasswordResetSender:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, *, recipient, reset_url):
        self.messages.append({"recipient": recipient, "reset_url": reset_url})


@pytest.mark.asyncio
async def test_request_password_reset_creates_token_and_sends_email_for_active_user() -> None:
    user = SimpleNamespace(id=7, email="user@example.com", status=UserStatus.ACTIVE)
    users = FakeUserRepository(user)
    tokens = FakePasswordResetTokenRepository()
    sender = FakePasswordResetSender()
    service = AuthService(
        users,
        Settings(jwt_secret_key="test-secret", app_base_url="https://example.test"),
        password_reset_tokens=tokens,
        password_reset_sender=sender,
    )

    await service.request_password_reset("User@Example.com")

    assert tokens.invalidated_user_ids == [7]
    assert tokens.created.user_id == 7
    assert len(tokens.created.token_hash) == 64
    assert sender.messages[0]["recipient"] == "user@example.com"
    assert sender.messages[0]["reset_url"].startswith("https://example.test/reset-password?token=")
    assert tokens.created.token_hash not in sender.messages[0]["reset_url"]


@pytest.mark.asyncio
async def test_request_password_reset_does_not_reveal_missing_user() -> None:
    users = FakeUserRepository()
    tokens = FakePasswordResetTokenRepository()
    sender = FakePasswordResetSender()
    service = AuthService(
        users,
        Settings(jwt_secret_key="test-secret", app_base_url="https://example.test"),
        password_reset_tokens=tokens,
        password_reset_sender=sender,
    )

    await service.request_password_reset("missing@example.com")

    assert tokens.created is None
    assert sender.messages == []


@pytest.mark.asyncio
async def test_confirm_password_reset_changes_password_and_consumes_token() -> None:
    settings = Settings(jwt_secret_key="test-secret")
    user = SimpleNamespace(
        id=9,
        email="user@example.com",
        status=UserStatus.ACTIVE,
        role=UserRole.USER,
        password_hash=hash_password("old-password", settings),
    )
    users = FakeUserRepository(user)
    tokens = FakePasswordResetTokenRepository()
    service = AuthService(
        users,
        settings,
        password_reset_tokens=tokens,
        password_reset_sender=FakePasswordResetSender(),
    )
    raw_token = await service.request_password_reset("user@example.com", base_url="https://example.test")

    await service.confirm_password_reset(raw_token, "new-password")

    logged_in, _token, _expires_at = await service.login(
        LoginRequest(email="user@example.com", password="new-password")
    )
    assert logged_in is user
    assert tokens.created.used_at is not None


@pytest.mark.asyncio
async def test_confirm_password_reset_rejects_reused_token() -> None:
    settings = Settings(jwt_secret_key="test-secret")
    user = SimpleNamespace(
        id=9,
        email="user@example.com",
        status=UserStatus.ACTIVE,
        role=UserRole.USER,
        password_hash=hash_password("old-password", settings),
    )
    tokens = FakePasswordResetTokenRepository()
    service = AuthService(
        FakeUserRepository(user),
        settings,
        password_reset_tokens=tokens,
        password_reset_sender=FakePasswordResetSender(),
    )
    raw_token = await service.request_password_reset("user@example.com", base_url="https://example.test")
    await service.confirm_password_reset(raw_token, "new-password")

    with pytest.raises(AuthenticationError):
        await service.confirm_password_reset(raw_token, "another-password")


@pytest.mark.asyncio
async def test_confirm_password_reset_rejects_expired_token() -> None:
    settings = Settings(jwt_secret_key="test-secret")
    token = SimpleNamespace(
        user_id=5,
        token_hash="unused",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        used_at=None,
    )
    service = AuthService(
        FakeUserRepository(),
        settings,
        password_reset_tokens=FakePasswordResetTokenRepository(token),
        password_reset_sender=FakePasswordResetSender(),
    )

    with pytest.raises(AuthenticationError):
        await service.confirm_password_reset("expired-token", "new-password")


@pytest.mark.asyncio
async def test_request_password_reset_skips_disabled_user() -> None:
    user = SimpleNamespace(id=7, email="user@example.com", status=UserStatus.DISABLED)
    tokens = FakePasswordResetTokenRepository()
    sender = FakePasswordResetSender()
    service = AuthService(
        FakeUserRepository(user),
        Settings(jwt_secret_key="test-secret", app_base_url="https://example.test"),
        password_reset_tokens=tokens,
        password_reset_sender=sender,
    )

    await service.request_password_reset("user@example.com")

    assert tokens.created is None
    assert sender.messages == []

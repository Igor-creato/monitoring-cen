import hmac
from collections.abc import AsyncIterator

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import UserRole
from app.domain.exceptions import AuthenticationError, AuthorizationError
from app.infra.config import Settings, get_settings
from app.infra.db.models.user import UserModel
from app.infra.db.session import async_session_factory
from app.infra.http import create_http_client
from app.infra.security import decode_jwt
from app.product_fetching.factory import create_product_provider
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.service_setting_repository import ServiceSettingRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.monitor_service import MonitorService
from app.services.price_check_service import PriceCheckService
from app.services.product_service import ProductService
from app.services.runtime_settings import resolve_internal_api_token, resolve_runtime_settings

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def get_monitor_repository(
    session: AsyncSession = Depends(get_db_session),
) -> MonitorRepository:
    return MonitorRepository(session)


def get_price_check_repository(
    session: AsyncSession = Depends(get_db_session),
) -> PriceCheckRepository:
    return PriceCheckRepository(session)


def get_notification_repository(
    session: AsyncSession = Depends(get_db_session),
) -> NotificationRepository:
    return NotificationRepository(session)


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> UserRepository:
    return UserRepository(session)


def get_product_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ProductRepository:
    return ProductRepository(session)


def get_service_setting_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ServiceSettingRepository:
    return ServiceSettingRepository(session)


def get_monitor_service(
    monitor_repository: MonitorRepository = Depends(get_monitor_repository),
) -> MonitorService:
    return MonitorService(monitor_repository)


async def get_price_check_service(
    monitor_repository: MonitorRepository = Depends(get_monitor_repository),
    price_check_repository: PriceCheckRepository = Depends(get_price_check_repository),
    product_repository: ProductRepository = Depends(get_product_repository),
    notification_repository: NotificationRepository = Depends(get_notification_repository),
    user_repository: UserRepository = Depends(get_user_repository),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[PriceCheckService]:
    http_client = create_http_client()
    try:
        runtime_settings = await resolve_runtime_settings(session, settings)
        yield PriceCheckService(
            monitor_repository,
            price_check_repository,
            product_repository=product_repository,
            notification_repository=notification_repository,
            user_repository=user_repository,
            product_provider=create_product_provider(http_client, settings=runtime_settings),
            notification_dedupe_window_seconds=settings.notification_dedupe_window_seconds,
        )
    finally:
        await http_client.aclose()


def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(user_repository, settings)


def get_product_service(
    product_repository: ProductRepository = Depends(get_product_repository),
    price_check_repository: PriceCheckRepository = Depends(get_price_check_repository),
) -> ProductService:
    return ProductService(product_repository, price_check_repository)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user_repository: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> UserModel:
    if credentials is None:
        raise AuthenticationError("Missing bearer token")

    payload = decode_jwt(credentials.credentials, settings)
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise AuthenticationError("Invalid access token")

    return await user_repository.get_active_or_raise(int(subject))


async def require_admin_user(
    current_user: UserModel = Depends(get_current_user),
) -> UserModel:
    if current_user.role != UserRole.ADMIN:
        raise AuthorizationError("Admin access required")
    return current_user


async def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> None:
    internal_token = await resolve_internal_api_token(session, settings)
    if internal_token is None:
        return
    if x_internal_token is None or not hmac.compare_digest(x_internal_token, internal_token):
        raise AuthorizationError("Invalid internal API token")

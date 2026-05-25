from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_auth_service,
    get_db_session,
    get_monitor_repository,
    get_monitor_service,
    get_price_check_repository,
    get_settings,
    get_user_repository,
)
from app.api.v1.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
)
from app.api.v1.schemas.monitor import MonitorCreateRequest, MonitorUpdateRequest
from app.common.clock import utc_now
from app.domain.enums import (
    AvailabilityStatus,
    CheckStatus,
    Marketplace,
    MonitorStatus,
    NotificationStatus,
    UserRole,
    UserStatus,
)
from app.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    DomainError,
    EntityNotFoundError,
)
from app.infra.config import Settings
from app.infra.db.models.audit_log import AuditLogModel
from app.infra.db.models.monitor import MonitorModel
from app.infra.db.models.notification import NotificationModel
from app.infra.db.models.parser_error import ParserErrorModel
from app.infra.db.models.price_check import PriceCheckModel
from app.infra.db.models.user import UserModel
from app.infra.security import decode_jwt, hash_password
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.repositories.service_setting_repository import ServiceSettingRepository
from app.repositories.user_repository import UserRepository
from app.scheduler.enqueue import enqueue_monitor_check
from app.services.auth_service import AuthService
from app.services.monitor_service import MonitorService
from app.services.runtime_settings import RuntimeSettingsError, RuntimeSettingsService

BASE_DIR = Path(__file__).resolve().parent
static_directory = BASE_DIR / "static"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

AUTH_COOKIE = "pm_access_token"
CSRF_COOKIE = "pm_csrf_token"
AVAILABLE_MONITOR_MARKETPLACES = (Marketplace.WILDBERRIES,)

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _current_user(request, users, settings)
    return _redirect("/monitors" if user else "/login")


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    if await _current_user(request, users, settings):
        return _redirect("/monitors")
    return _render(request, "auth/register.html", {"title": "Регистрация"}, settings)


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _valid_csrf(request, csrf_token, settings):
        return _form_error(request, "auth/register.html", "Сессия формы устарела.", settings)

    form = {"email": email}
    try:
        payload = RegisterRequest(email=email.strip(), password=password)
        user, token, _expires_at = await service.register(payload)
    except ValidationError as exc:
        return _form_error(request, "auth/register.html", _validation_message(exc), settings, form)
    except ConflictError:
        return _form_error(
            request,
            "auth/register.html",
            "Пользователь уже существует.",
            settings,
            form,
        )

    response = _redirect("/monitors", status.HTTP_303_SEE_OTHER)
    _set_auth_cookie(response, token, settings)
    _rotate_csrf(response, settings)
    response.headers["x-authenticated-user"] = str(user.id)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    reset: str | None = Query(default=None),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    if await _current_user(request, users, settings):
        return _redirect("/monitors")
    return _render(
        request,
        "auth/login.html",
        {"title": "Вход", "reset_success": reset == "success"},
        settings,
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _valid_csrf(request, csrf_token, settings):
        return _form_error(request, "auth/login.html", "Сессия формы устарела.", settings)

    form = {"email": email}
    try:
        payload = LoginRequest(email=email.strip(), password=password)
        _user, token, _expires_at = await service.login(payload)
    except (ValidationError, AuthenticationError):
        return _form_error(request, "auth/login.html", "Неверный email или пароль.", settings, form)

    response = _redirect("/monitors", status.HTTP_303_SEE_OTHER)
    _set_auth_cookie(response, token, settings)
    _rotate_csrf(response, settings)
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    if await _current_user(request, users, settings):
        return _redirect("/monitors")
    return _render(
        request,
        "auth/forgot_password.html",
        {"title": "Восстановление пароля", "submitted": False},
        settings,
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    csrf_token: str = Form(...),
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _valid_csrf(request, csrf_token, settings):
        return _form_error(
            request,
            "auth/forgot_password.html",
            "Сессия формы устарела.",
            settings,
            {"email": email},
        )

    try:
        payload = PasswordResetRequest(email=email.strip())
    except ValidationError as exc:
        return _form_error(
            request,
            "auth/forgot_password.html",
            _validation_message(exc),
            settings,
            {"email": email},
        )

    await service.request_password_reset(payload.email, base_url=_request_origin(request))
    return _render(
        request,
        "auth/forgot_password.html",
        {
            "title": "Восстановление пароля",
            "submitted": True,
            "form": {"email": email},
        },
        settings,
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str = Query(""),
    settings: Settings = Depends(get_settings),
) -> Response:
    return _render(
        request,
        "auth/reset_password.html",
        {"title": "Новый пароль", "form": {"token": token}},
        settings,
    )


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    form = {"token": token}
    if not _valid_csrf(request, csrf_token, settings):
        return _form_error(
            request,
            "auth/reset_password.html",
            "Сессия формы устарела.",
            settings,
            form,
        )

    try:
        payload = PasswordResetConfirmRequest(token=token, password=password)
        await service.confirm_password_reset(payload.token, payload.password)
    except ValidationError as exc:
        return _form_error(
            request,
            "auth/reset_password.html",
            _validation_message(exc),
            settings,
            form,
        )
    except AuthenticationError:
        return _form_error(
            request,
            "auth/reset_password.html",
            "Ссылка для сброса пароля недействительна или устарела.",
            settings,
            form,
        )

    return _redirect("/login?reset=success", status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(
    request: Request,
    csrf_token: str = Form(...),
    settings: Settings = Depends(get_settings),
) -> Response:
    response = _redirect("/login", status.HTTP_303_SEE_OTHER)
    response.delete_cookie(AUTH_COOKIE, path="/")
    if _valid_csrf(request, csrf_token, settings):
        _rotate_csrf(response, settings)
    return response


@router.get("/monitors", response_class=HTMLResponse)
async def monitors_page(
    request: Request,
    status_filter: MonitorStatus | None = Query(default=None, alias="status"),
    users: UserRepository = Depends(get_user_repository),
    service: MonitorService = Depends(get_monitor_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    total, monitors = await service.list_monitors(user.id, 100, 0, status_filter)
    stats = _monitor_stats(monitors)
    return _render(
        request,
        "monitors/index.html",
        {
            "title": "Мониторинги",
            "user": user,
            "monitors": monitors,
            "total": total,
            "stats": stats,
            "status_filter": status_filter,
            "statuses": list(MonitorStatus),
        },
        settings,
    )


@router.get("/monitors/new", response_class=HTMLResponse)
async def monitor_new_page(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    return _render(
        request,
        "monitors/new.html",
        {
            "title": "Новый мониторинг",
            "user": user,
            "form": {
                "marketplace": Marketplace.WILDBERRIES.value,
                "notification_channel": user.default_notification_channel or "",
            },
            "marketplaces": AVAILABLE_MONITOR_MARKETPLACES,
        },
        settings,
    )


@router.post("/monitors", response_class=HTMLResponse)
async def monitor_create(
    request: Request,
    marketplace: str = Form(Marketplace.WILDBERRIES.value),
    url: str = Form(...),
    target_price: str = Form(""),
    check_interval_seconds: int = Form(3600),
    notification_channel: str = Form(""),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    service: MonitorService = Depends(get_monitor_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    form = {
        "marketplace": marketplace,
        "url": url,
        "target_price": target_price,
        "check_interval_seconds": check_interval_seconds,
        "notification_channel": notification_channel,
    }
    if not _valid_csrf(request, csrf_token, settings):
        return _form_error(
            request,
            "monitors/new.html",
            "Сессия формы устарела.",
            settings,
            form,
            user,
        )

    try:
        channel = _clean_channel(notification_channel)
        if channel is None and user.notifications_enabled:
            channel = user.default_notification_channel
        payload = MonitorCreateRequest(
            url=url.strip(),
            marketplace=_parse_marketplace(marketplace),
            target_price=_optional_decimal(target_price),
            check_interval_seconds=check_interval_seconds,
            notification_channel=channel if user.notifications_enabled else None,
        )
        monitor = await service.create_monitor(user.id, payload)
    except (ValueError, ValidationError, DomainError) as exc:
        return _form_error(
            request,
            "monitors/new.html",
            _error_message(exc),
            settings,
            form,
            user,
        )

    return _redirect(f"/monitors/{monitor.id}", status.HTTP_303_SEE_OTHER)


@router.get("/monitors/{monitor_id}", response_class=HTMLResponse)
async def monitor_detail(
    monitor_id: int,
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    monitors: MonitorRepository = Depends(get_monitor_repository),
    checks: PriceCheckRepository = Depends(get_price_check_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    try:
        monitor = await monitors.get_for_user_or_raise(monitor_id, user.id)
    except EntityNotFoundError:
        return _not_found(request, user, settings)
    _total, history = await checks.list_by_monitor_for_user(monitor.id, user.id, 8, 0)
    return _render(
        request,
        "monitors/detail.html",
        {
            "title": f"Мониторинг #{monitor.id}",
            "user": user,
            "monitor": monitor,
            "history": history,
            "statuses": [MonitorStatus.ACTIVE, MonitorStatus.PAUSED, MonitorStatus.DISABLED],
        },
        settings,
    )


@router.post("/monitors/{monitor_id}", response_class=HTMLResponse)
async def monitor_update(
    monitor_id: int,
    request: Request,
    target_price: str = Form(""),
    check_interval_seconds: int = Form(3600),
    notification_channel: str = Form(""),
    monitor_status: MonitorStatus = Form(..., alias="status"),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    service: MonitorService = Depends(get_monitor_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    if not _valid_csrf(request, csrf_token, settings):
        return _redirect(f"/monitors/{monitor_id}?error=csrf", status.HTTP_303_SEE_OTHER)

    try:
        payload = MonitorUpdateRequest(
            target_price=_optional_decimal(target_price),
            check_interval_seconds=check_interval_seconds,
            notification_channel=_clean_channel(notification_channel),
            status=monitor_status,
        )
        await service.update_monitor(user.id, monitor_id, payload)
    except (ValueError, ValidationError, DomainError):
        return _redirect(f"/monitors/{monitor_id}?error=validation", status.HTTP_303_SEE_OTHER)

    return _redirect(f"/monitors/{monitor_id}", status.HTTP_303_SEE_OTHER)


@router.post("/monitors/{monitor_id}/delete")
async def monitor_delete(
    monitor_id: int,
    request: Request,
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    service: MonitorService = Depends(get_monitor_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    if _valid_csrf(request, csrf_token, settings):
        await service.delete_monitor(user.id, monitor_id)
    return _redirect("/monitors", status.HTTP_303_SEE_OTHER)


@router.get("/monitors/{monitor_id}/history", response_class=HTMLResponse)
async def monitor_history(
    monitor_id: int,
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    monitors: MonitorRepository = Depends(get_monitor_repository),
    checks: PriceCheckRepository = Depends(get_price_check_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    try:
        monitor = await monitors.get_for_user_or_raise(monitor_id, user.id)
    except EntityNotFoundError:
        return _not_found(request, user, settings)
    total, history = await checks.list_by_monitor_for_user(monitor.id, user.id, 200, 0)
    return _render(
        request,
        "monitors/history.html",
        {
            "title": f"История #{monitor.id}",
            "user": user,
            "monitor": monitor,
            "history": history,
            "total": total,
        },
        settings,
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    service: MonitorService = Depends(get_monitor_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    total, monitors = await service.list_monitors(user.id, 200, 0)
    channels = sorted(
        {monitor.notification_channel for monitor in monitors if monitor.notification_channel}
    )
    return _render(
        request,
        "profile/index.html",
        {
            "title": "Профиль",
            "user": user,
            "monitors_count": total,
            "channels": channels,
        },
        settings,
    )


@router.post("/profile", response_class=HTMLResponse)
async def profile_update(
    request: Request,
    notifications_enabled: str | None = Form(None),
    default_notification_channel: str = Form(""),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = await _require_user(request, users, settings)
    if not _valid_csrf(request, csrf_token, settings):
        return _redirect("/profile?error=csrf", status.HTTP_303_SEE_OTHER)

    channel = _clean_channel(default_notification_channel)
    if channel is not None and len(channel) > 64:
        return _redirect("/profile?error=channel", status.HTTP_303_SEE_OTHER)

    user.notifications_enabled = notifications_enabled == "on"
    user.default_notification_channel = channel
    await users.session.commit()
    return _redirect("/profile?saved=1", status.HTTP_303_SEE_OTHER)


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    since = utc_now() - timedelta(hours=24)
    stats = {
        "users": await session.scalar(select(func.count()).select_from(UserModel)) or 0,
        "admins": await users.count_admins(),
        "monitors": await session.scalar(select(func.count()).select_from(MonitorModel)) or 0,
        "active_monitors": await session.scalar(
            select(func.count())
            .select_from(MonitorModel)
            .where(MonitorModel.status == MonitorStatus.ACTIVE)
            .where(MonitorModel.deleted_at.is_(None))
        )
        or 0,
        "error_monitors": await session.scalar(
            select(func.count())
            .select_from(MonitorModel)
            .where(MonitorModel.status.in_((MonitorStatus.ERROR, MonitorStatus.FAILED)))
            .where(MonitorModel.deleted_at.is_(None))
        )
        or 0,
        "checks_24h": await session.scalar(
            select(func.count())
            .select_from(PriceCheckModel)
            .where(PriceCheckModel.checked_at >= since)
        )
        or 0,
        "pending_notifications": await session.scalar(
            select(func.count())
            .select_from(NotificationModel)
            .where(NotificationModel.status == NotificationStatus.PENDING)
        )
        or 0,
        "failed_notifications": await session.scalar(
            select(func.count())
            .select_from(NotificationModel)
            .where(NotificationModel.status == NotificationStatus.FAILED)
        )
        or 0,
    }
    try:
        token_statuses = await RuntimeSettingsService(
            ServiceSettingRepository(session),
            settings,
        ).list_statuses()
        settings_error = None
    except RuntimeSettingsError as exc:
        token_statuses = []
        settings_error = str(exc)
    return _render(
        request,
        "admin/dashboard.html",
        {
            "title": "Админка",
            "user": admin,
            "stats": stats,
            "token_statuses": token_statuses,
            "settings_error": settings_error,
        },
        settings,
    )


@router.get("/admin/docs", response_class=HTMLResponse)
async def admin_docs_page(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    admin = await _require_admin(request, users, settings)
    return _render(
        request,
        "admin/docs.html",
        {"title": "Документация", "user": admin},
        settings,
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    q: str | None = Query(default=None),
    role: UserRole | None = Query(default=None),
    user_status: UserStatus | None = Query(default=None, alias="status"),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    admin = await _require_admin(request, users, settings)
    total, items = await users.list_users(200, 0, q, user_status, role)
    return _render(
        request,
        "admin/users.html",
        {
            "title": "Пользователи",
            "user": admin,
            "users": items,
            "total": total,
            "q": q or "",
            "role_filter": role,
            "status_filter": user_status,
            "roles": list(UserRole),
            "user_statuses": list(UserStatus),
        },
        settings,
    )


@router.post("/admin/users", response_class=HTMLResponse)
async def admin_user_create(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: UserRole = Form(UserRole.USER),
    user_status: UserStatus = Form(UserStatus.ACTIVE, alias="status"),
    notifications_enabled: str | None = Form(None),
    default_notification_channel: str = Form(""),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    if not _valid_csrf(request, csrf_token, settings):
        return _redirect("/admin/users?error=csrf", status.HTTP_303_SEE_OTHER)
    try:
        user = await users.create(
            email=email.strip().lower(),
            password_hash=hash_password(password, settings),
            role=role,
        )
        user.status = user_status
        user.notifications_enabled = notifications_enabled == "on"
        user.default_notification_channel = _clean_channel(default_notification_channel)
        await users.session.commit()
    except ConflictError:
        return _redirect("/admin/users?error=conflict", status.HTTP_303_SEE_OTHER)
    await _audit(session, admin, request, "user", user.id, "create", None, _user_audit(user))
    return _redirect("/admin/users?saved=1", status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}", response_class=HTMLResponse)
async def admin_user_update(
    user_id: int,
    request: Request,
    role: UserRole = Form(...),
    user_status: UserStatus = Form(..., alias="status"),
    notifications_enabled: str | None = Form(None),
    default_notification_channel: str = Form(""),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    if not _valid_csrf(request, csrf_token, settings):
        return _redirect("/admin/users?error=csrf", status.HTTP_303_SEE_OTHER)
    target = await users.get(user_id)
    if target is None:
        return _redirect("/admin/users?error=not_found", status.HTTP_303_SEE_OTHER)
    if target.id == admin.id and (role != UserRole.ADMIN or user_status != UserStatus.ACTIVE):
        return _redirect("/admin/users?error=self_lock", status.HTTP_303_SEE_OTHER)
    if (
        target.role == UserRole.ADMIN
        and target.status == UserStatus.ACTIVE
        and (role != UserRole.ADMIN or user_status != UserStatus.ACTIVE)
        and await users.count_admins() <= 1
    ):
        return _redirect("/admin/users?error=last_admin", status.HTTP_303_SEE_OTHER)

    old_values = _user_audit(target)
    target.role = role
    target.status = user_status
    target.notifications_enabled = notifications_enabled == "on"
    target.default_notification_channel = _clean_channel(default_notification_channel)
    await users.session.commit()
    await users.session.refresh(target)
    await _audit(
        session,
        admin,
        request,
        "user",
        target.id,
        "update",
        old_values,
        _user_audit(target),
    )
    return _redirect("/admin/users?saved=1", status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/password", response_class=HTMLResponse)
async def admin_user_password(
    user_id: int,
    request: Request,
    password: str = Form(...),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    if not _valid_csrf(request, csrf_token, settings):
        return _redirect("/admin/users?error=csrf", status.HTTP_303_SEE_OTHER)
    target = await users.get(user_id)
    if target is None or len(password) < 8:
        return _redirect("/admin/users?error=password", status.HTTP_303_SEE_OTHER)
    target.password_hash = hash_password(password, settings)
    await users.session.commit()
    await _audit(session, admin, request, "user", target.id, "reset_password", None, None)
    return _redirect("/admin/users?saved=1", status.HTTP_303_SEE_OTHER)


@router.get("/admin/tokens", response_class=HTMLResponse)
async def admin_tokens_page(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    service = RuntimeSettingsService(ServiceSettingRepository(session), settings)
    try:
        token_statuses = await service.list_statuses()
        error = None
    except RuntimeSettingsError as exc:
        token_statuses = []
        error = str(exc)
    return _render(
        request,
        "admin/tokens.html",
        {"title": "Токены", "user": admin, "token_statuses": token_statuses, "error": error},
        settings,
    )


@router.post("/admin/tokens", response_class=HTMLResponse)
async def admin_token_update(
    request: Request,
    key: str = Form(...),
    value: str = Form(...),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    if not _valid_csrf(request, csrf_token, settings):
        return _redirect("/admin/tokens?error=csrf", status.HTTP_303_SEE_OTHER)
    service = RuntimeSettingsService(ServiceSettingRepository(session), settings)
    try:
        if key in {
            "apify_api_token",
            "zyte_api_key",
            "internal_api_token",
            "wildberries_proxy_url",
        }:
            await service.set_secret(key, value, admin.id)
        else:
            await service.set_plain(key, value, admin.id)
    except RuntimeSettingsError:
        return _redirect("/admin/tokens?error=settings", status.HTTP_303_SEE_OTHER)
    await _audit(
        session,
        admin,
        request,
        "service_setting",
        None,
        f"update:{key}",
        None,
        {"key": key},
    )
    return _redirect("/admin/tokens?saved=1", status.HTTP_303_SEE_OTHER)


@router.post("/admin/tokens/clear", response_class=HTMLResponse)
async def admin_token_clear(
    request: Request,
    key: str = Form(...),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    if _valid_csrf(request, csrf_token, settings):
        service = RuntimeSettingsService(ServiceSettingRepository(session), settings)
        await service.clear(key)
        await _audit(
            session,
            admin,
            request,
            "service_setting",
            None,
            f"clear:{key}",
            {"key": key},
            None,
        )
    return _redirect("/admin/tokens?saved=1", status.HTTP_303_SEE_OTHER)


@router.get("/admin/monitors", response_class=HTMLResponse)
async def admin_monitors_page(
    request: Request,
    monitor_status: MonitorStatus | None = Query(default=None, alias="status"),
    user_id: int | None = Query(default=None),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    filters = []
    if monitor_status is not None:
        filters.append(MonitorModel.status == monitor_status)
    if user_id is not None:
        filters.append(MonitorModel.user_id == user_id)
    total = (
        await session.scalar(select(func.count()).select_from(MonitorModel).where(*filters))
        or 0
    )
    result = await session.execute(
        select(MonitorModel)
        .where(*filters)
        .order_by(MonitorModel.created_at.desc(), MonitorModel.id.desc())
        .limit(200)
    )
    monitors = list(result.scalars().all())
    return _render(
        request,
        "admin/monitors.html",
        {
            "title": "Все мониторинги",
            "user": admin,
            "monitors": monitors,
            "total": total,
            "statuses": list(MonitorStatus),
            "status_filter": monitor_status,
            "user_id": user_id or "",
        },
        settings,
    )


@router.get("/admin/monitors/{monitor_id}", response_class=HTMLResponse)
async def admin_monitor_detail(
    monitor_id: int,
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    monitor = await MonitorRepository(session).get(monitor_id)
    if monitor is None:
        return _redirect("/admin/monitors?error=not_found", status.HTTP_303_SEE_OTHER)
    checks_result = await session.execute(
        select(PriceCheckModel)
        .where(PriceCheckModel.monitor_id == monitor.id)
        .order_by(PriceCheckModel.checked_at.desc(), PriceCheckModel.id.desc())
        .limit(25)
    )
    errors_result = await session.execute(
        select(ParserErrorModel)
        .where(ParserErrorModel.monitor_id == monitor.id)
        .order_by(ParserErrorModel.occurred_at.desc(), ParserErrorModel.id.desc())
        .limit(25)
    )
    return _render(
        request,
        "admin/monitor_detail.html",
        {
            "title": f"Мониторинг #{monitor.id}",
            "user": admin,
            "monitor": monitor,
            "history": list(checks_result.scalars().all()),
            "parser_errors": list(errors_result.scalars().all()),
            "statuses": [MonitorStatus.ACTIVE, MonitorStatus.PAUSED, MonitorStatus.DISABLED],
        },
        settings,
    )


@router.post("/admin/monitors/{monitor_id}/action", response_class=HTMLResponse)
async def admin_monitor_action(
    monitor_id: int,
    request: Request,
    action: str = Form(...),
    monitor_status: MonitorStatus | None = Form(None, alias="status"),
    csrf_token: str = Form(...),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    if not _valid_csrf(request, csrf_token, settings):
        return _redirect(f"/admin/monitors/{monitor_id}?error=csrf", status.HTTP_303_SEE_OTHER)
    repository = MonitorRepository(session)
    monitor = await repository.get(monitor_id)
    if monitor is None:
        return _redirect("/admin/monitors?error=not_found", status.HTTP_303_SEE_OTHER)
    old_values = {"status": monitor.status.value, "next_check_at": str(monitor.next_check_at)}
    if action == "status" and monitor_status is not None:
        await repository.update(monitor, {"status": monitor_status})
    elif action == "delete":
        await repository.soft_delete(monitor)
    elif action == "check":
        await enqueue_monitor_check(settings.redis_url, monitor.id)
    else:
        return _redirect(f"/admin/monitors/{monitor_id}?error=action", status.HTTP_303_SEE_OTHER)
    await _audit(
        session,
        admin,
        request,
        "monitor",
        monitor.id,
        action,
        old_values,
        {"status": monitor.status.value, "next_check_at": str(monitor.next_check_at)},
    )
    return _redirect(f"/admin/monitors/{monitor_id}?saved=1", status.HTTP_303_SEE_OTHER)


@router.get("/admin/notifications", response_class=HTMLResponse)
async def admin_notifications_page(
    request: Request,
    notification_status: NotificationStatus | None = Query(default=None, alias="status"),
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    filters = [NotificationModel.status == notification_status] if notification_status else []
    result = await session.execute(
        select(NotificationModel)
        .where(*filters)
        .order_by(NotificationModel.created_at.desc(), NotificationModel.id.desc())
        .limit(200)
    )
    return _render(
        request,
        "admin/notifications.html",
        {
            "title": "Уведомления",
            "user": admin,
            "notifications": list(result.scalars().all()),
            "statuses": list(NotificationStatus),
            "status_filter": notification_status,
        },
        settings,
    )


@router.get("/admin/errors", response_class=HTMLResponse)
async def admin_errors_page(
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    admin = await _require_admin(request, users, settings)
    parser_result = await session.execute(
        select(ParserErrorModel)
        .order_by(ParserErrorModel.occurred_at.desc(), ParserErrorModel.id.desc())
        .limit(100)
    )
    check_result = await session.execute(
        select(PriceCheckModel)
        .where(PriceCheckModel.status != CheckStatus.SUCCESS)
        .order_by(PriceCheckModel.checked_at.desc(), PriceCheckModel.id.desc())
        .limit(100)
    )
    return _render(
        request,
        "admin/errors.html",
        {
            "title": "Ошибки",
            "user": admin,
            "parser_errors": list(parser_result.scalars().all()),
            "failed_checks": list(check_result.scalars().all()),
        },
        settings,
    )


async def _current_user(
    request: Request,
    users: UserRepository,
    settings: Settings,
) -> UserModel | None:
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        return None
    try:
        payload = decode_jwt(token, settings)
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject.isdigit():
            return None
        return await users.get_active_or_raise(int(subject))
    except (AuthenticationError, EntityNotFoundError):
        return None


async def _require_user(
    request: Request,
    users: UserRepository,
    settings: Settings,
) -> UserModel:
    user = await _current_user(request, users, settings)
    if user is None:
        raise WebRedirect("/login")
    return user


async def _require_admin(
    request: Request,
    users: UserRepository,
    settings: Settings,
) -> UserModel:
    user = await _require_user(request, users, settings)
    if user.role != UserRole.ADMIN:
        raise WebRedirect("/monitors")
    return user


async def _audit(
    session: AsyncSession,
    user: UserModel,
    request: Request,
    entity_type: str,
    entity_id: int | None,
    action: str,
    old_values: dict[str, Any] | None,
    new_values: dict[str, Any] | None,
) -> None:
    session.add(
        AuditLogModel(
            user_id=user.id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            old_values=old_values,
            new_values=new_values,
        )
    )
    await session.commit()


def _user_audit(user: UserModel) -> dict[str, Any]:
    return {
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value,
        "notifications_enabled": user.notifications_enabled,
        "default_notification_channel": user.default_notification_channel,
    }


def _render(
    request: Request,
    template: str,
    context: dict[str, Any],
    settings: Settings,
    status_code: int = 200,
) -> Response:
    token = request.cookies.get(CSRF_COOKIE)
    if not token or not _valid_signed_token(token, settings):
        token = _csrf_token(settings)

    response = templates.TemplateResponse(
        request,
        template,
        {
            "request": request,
            "csrf_token": token,
            "current_path": request.url.path,
            "error": None,
            "form": {},
            "marketplaces": AVAILABLE_MONITOR_MARKETPLACES,
            **context,
        },
        status_code=status_code,
    )
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=True,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
        max_age=60 * 60 * 12,
    )
    return response


def _form_error(
    request: Request,
    template: str,
    message: str,
    settings: Settings,
    form: dict[str, Any] | None = None,
    user: UserModel | None = None,
) -> Response:
    return _render(
        request,
        template,
        {
            "title": "Ошибка формы",
            "error": message,
            "form": form or {},
            "user": user,
        },
        settings,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _not_found(request: Request, user: UserModel, settings: Settings) -> Response:
    return _render(
        request,
        "monitors/not_found.html",
        {"title": "Не найдено", "user": user},
        settings,
        status.HTTP_404_NOT_FOUND,
    )


def _redirect(url: str, status_code: int = status.HTTP_302_FOUND) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status_code)


def _request_origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _set_auth_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        AUTH_COOKIE,
        token,
        httponly=True,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
        max_age=settings.access_token_expire_minutes * 60,
    )


def _rotate_csrf(response: Response, settings: Settings) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        _csrf_token(settings),
        httponly=True,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
        max_age=60 * 60 * 12,
    )


def _csrf_token(settings: Settings) -> str:
    nonce = secrets.token_urlsafe(24)
    signature = _sign(nonce, settings)
    return f"{nonce}.{signature}"


def _valid_csrf(request: Request, submitted_token: str, settings: Settings) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE)
    return (
        bool(cookie_token)
        and hmac.compare_digest(cookie_token, submitted_token)
        and _valid_signed_token(cookie_token, settings)
    )


def _valid_signed_token(token: str, settings: Settings) -> bool:
    try:
        nonce, signature = token.rsplit(".", maxsplit=1)
    except ValueError:
        return False
    return hmac.compare_digest(signature, _sign(nonce, settings))


def _sign(value: str, settings: Settings) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        value.encode("utf-8"),
        "sha256",
    ).hexdigest()


def _secure_cookie(settings: Settings) -> bool:
    return settings.app_env.lower() not in {"local", "dev", "development", "test"}


def _optional_decimal(value: str) -> Decimal | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Price must be a valid number") from exc


def _clean_channel(value: str) -> str | None:
    value = value.strip()
    return value or None


def _parse_marketplace(value: str) -> Marketplace:
    try:
        marketplace = Marketplace(value.strip())
    except ValueError as exc:
        raise ValueError("Выбранный маркетплейс не поддерживается") from exc
    if marketplace not in AVAILABLE_MONITOR_MARKETPLACES:
        raise ValueError("Выбранный маркетплейс пока недоступен для мониторинга")
    return marketplace


def _monitor_stats(monitors: list[MonitorModel]) -> dict[str, int]:
    return {
        "active": sum(1 for item in monitors if item.status == MonitorStatus.ACTIVE),
        "paused": sum(1 for item in monitors if item.status == MonitorStatus.PAUSED),
        "errors": sum(
            1
            for item in monitors
            if item.status in {MonitorStatus.FAILED, MonitorStatus.ERROR, MonitorStatus.UNSUPPORTED}
        ),
    }


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", ()))
    message = first.get("msg", "Проверьте поля формы.")
    return f"{field}: {message}" if field else str(message)


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return _validation_message(exc)
    return str(exc) or "Проверьте поля формы."


def _format_money(value: Decimal | None, currency: str | None = None) -> str:
    if value is None:
        return "Нет данных"
    suffix = f" {currency}" if currency else ""
    return f"{value:,.2f}".replace(",", " ") + suffix


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "Еще не было"
    return value.strftime("%d.%m.%Y %H:%M")


def _interval_label(seconds: int | None) -> str:
    if seconds is None:
        return "Не задан"
    if seconds < 3600:
        return f"{seconds // 60} мин"
    if seconds < 86_400:
        return f"{seconds // 3600} ч"
    return f"{seconds // 86_400} дн"


MONITOR_STATUS_LABELS = {
    MonitorStatus.DRAFT: "Черновик",
    MonitorStatus.ACTIVE: "Активен",
    MonitorStatus.PAUSED: "На паузе",
    MonitorStatus.TRIGGERED: "Сработал",
    MonitorStatus.FAILED: "Сбой",
    MonitorStatus.ERROR: "Ошибка",
    MonitorStatus.UNSUPPORTED: "Не поддерживается",
    MonitorStatus.DISABLED: "Отключен",
    MonitorStatus.DELETED: "Удален",
}

CHECK_STATUS_LABELS = {
    CheckStatus.SUCCESS: "Успешно",
    CheckStatus.FAILED: "Сбой",
    CheckStatus.NOT_MODIFIED: "Без изменений",
    CheckStatus.BLOCKED: "Заблокировано",
    CheckStatus.TIMEOUT: "Таймаут",
    CheckStatus.PARSE_ERROR: "Ошибка разбора",
    CheckStatus.NETWORK_ERROR: "Ошибка сети",
}

AVAILABILITY_LABELS = {
    AvailabilityStatus.IN_STOCK: "В наличии",
    AvailabilityStatus.OUT_OF_STOCK: "Нет в наличии",
    AvailabilityStatus.PREORDER: "Предзаказ",
    AvailabilityStatus.UNKNOWN: "Неизвестно",
    AvailabilityStatus.UNAVAILABLE: "Недоступно",
}

MARKETPLACE_LABELS = {
    Marketplace.WILDBERRIES: "Wildberries",
    Marketplace.OZON: "Ozon",
    Marketplace.YANDEX_MARKET: "Яндекс Маркет",
    Marketplace.UNKNOWN: "Неизвестно",
}

USER_STATUS_LABELS = {
    UserStatus.ACTIVE: "Активен",
    UserStatus.DISABLED: "Отключен",
    UserStatus.DELETED: "Удален",
}

USER_ROLE_LABELS = {
    UserRole.USER: "Пользователь",
    UserRole.ADMIN: "Администратор",
}

NOTIFICATION_STATUS_LABELS = {
    NotificationStatus.PENDING: "Ожидает отправки",
    NotificationStatus.PROCESSING: "Отправляется",
    NotificationStatus.SENT: "Отправлено",
    NotificationStatus.FAILED: "Ошибка отправки",
    NotificationStatus.SKIPPED: "Пропущено",
    NotificationStatus.DUPLICATED: "Дубликат",
}

RUNTIME_SETTING_LABELS = {
    "product_fetch_provider": "Поставщик данных о товарах",
    "wildberries_proxy_url": "Прокси Wildberries",
    "wildberries_dest": "Регион доставки Wildberries",
    "wildberries_request_timeout_seconds": "Таймаут запроса Wildberries",
    "wildberries_basket_max_host": "Максимальный номер basket Wildberries",
    "apify_actor_id": "Идентификатор обработчика Apify",
    "apify_base_url": "Адрес API Apify",
    "apify_api_token": "Токен API Apify",
    "zyte_api_url": "Адрес API Zyte",
    "zyte_api_key": "Ключ API Zyte",
    "internal_api_token": "Внутренний API-токен",
}

RUNTIME_SETTING_VALUE_LABELS = {
    "wildberries_direct": "Wildberries напрямую",
    "apify": "Apify",
    "zyte": "Zyte",
    "mock": "Mock",
}

RUNTIME_SETTING_SOURCE_LABELS = {
    "db": "Из админки",
    "env": "Из .env",
    "missing": "Не задано",
}

ADMIN_ERROR_LABELS = {
    "csrf": "сессия формы устарела",
    "conflict": "пользователь уже существует",
    "not_found": "запись не найдена",
    "self_lock": "нельзя заблокировать собственный аккаунт администратора",
    "last_admin": "нельзя отключить последнего активного администратора",
    "password": "пароль должен быть не короче 8 символов",
    "settings": "настройку не удалось сохранить",
}

RUNTIME_SETTINGS_ERROR_LABELS = {
    "Setting value cannot be empty": "Значение настройки не может быть пустым",
    "Secret value cannot be empty": "Секретное значение не может быть пустым",
    "ADMIN_SECRETS_KEY is required for encrypted settings": (
        "Для сохранения секретов задайте ADMIN_SECRETS_KEY"
    ),
    "ADMIN_SECRETS_KEY must be a valid Fernet key": (
        "ADMIN_SECRETS_KEY должен быть корректным ключом Fernet"
    ),
}


def _enum_label(value: Any, labels: dict[Any, str]) -> str:
    if value is None:
        return "Не задан"
    if value in labels:
        return labels[value]
    for enum_value, label in labels.items():
        if getattr(enum_value, "value", None) == value:
            return label
    try:
        return labels[value.__class__(value)]
    except (ValueError, TypeError):
        return str(value)


def _monitor_status_label(value: Any) -> str:
    return _enum_label(value, MONITOR_STATUS_LABELS)


def _check_status_label(value: Any) -> str:
    return _enum_label(value, CHECK_STATUS_LABELS)


def _availability_label(value: Any) -> str:
    return _enum_label(value, AVAILABILITY_LABELS)


def _marketplace_label(value: Any) -> str:
    return _enum_label(value, MARKETPLACE_LABELS)


def _user_status_label(value: Any) -> str:
    return _enum_label(value, USER_STATUS_LABELS)


def _user_role_label(value: Any) -> str:
    return _enum_label(value, USER_ROLE_LABELS)


def _notification_status_label(value: Any) -> str:
    return _enum_label(value, NOTIFICATION_STATUS_LABELS)


def _runtime_setting_label(value: Any) -> str:
    return RUNTIME_SETTING_LABELS.get(str(value), str(value))


def _runtime_setting_source_label(value: Any) -> str:
    return RUNTIME_SETTING_SOURCE_LABELS.get(str(value), str(value))


def _runtime_setting_value_label(value: Any) -> str:
    return RUNTIME_SETTING_VALUE_LABELS.get(str(value), str(value))


def _runtime_setting_updated_label(value: Any) -> str:
    return _format_dt(value) if value else "Из .env или значения по умолчанию"


def _admin_error_label(value: Any) -> str:
    return ADMIN_ERROR_LABELS.get(str(value), str(value))


def _runtime_settings_error_label(value: Any) -> str:
    text = str(value)
    if text.startswith(("Unsupported plain setting", "Unsupported secret setting")):
        return "Эта настройка не поддерживается"
    if text.startswith("Unsupported setting"):
        return "Эта настройка не поддерживается"
    if text.startswith("Cannot decrypt setting"):
        return "Не удалось расшифровать сохраненное значение"
    return RUNTIME_SETTINGS_ERROR_LABELS.get(text, text)


templates.env.filters["money"] = _format_money
templates.env.filters["dt"] = _format_dt
templates.env.filters["interval"] = _interval_label
templates.env.filters["monitor_status_label"] = _monitor_status_label
templates.env.filters["check_status_label"] = _check_status_label
templates.env.filters["availability_label"] = _availability_label
templates.env.filters["marketplace_label"] = _marketplace_label
templates.env.filters["user_status_label"] = _user_status_label
templates.env.filters["user_role_label"] = _user_role_label
templates.env.filters["notification_status_label"] = _notification_status_label
templates.env.filters["runtime_setting_label"] = _runtime_setting_label
templates.env.filters["runtime_setting_source_label"] = _runtime_setting_source_label
templates.env.filters["runtime_setting_value_label"] = _runtime_setting_value_label
templates.env.filters["runtime_setting_updated_label"] = _runtime_setting_updated_label
templates.env.filters["admin_error_label"] = _admin_error_label
templates.env.filters["runtime_settings_error_label"] = _runtime_settings_error_label


class WebRedirect(Exception):
    def __init__(self, url: str):
        self.url = url


async def web_redirect_handler(request: Request, exc: WebRedirect) -> RedirectResponse:
    return _redirect(exc.url)

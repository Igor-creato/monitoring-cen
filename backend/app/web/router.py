from __future__ import annotations

import hmac
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.api.deps import (
    get_auth_service,
    get_monitor_repository,
    get_monitor_service,
    get_price_check_repository,
    get_settings,
    get_user_repository,
)
from app.api.v1.schemas.auth import LoginRequest, RegisterRequest
from app.api.v1.schemas.monitor import MonitorCreateRequest, MonitorUpdateRequest
from app.domain.enums import MonitorStatus
from app.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    DomainError,
    EntityNotFoundError,
)
from app.infra.config import Settings
from app.infra.db.models.monitor import MonitorModel
from app.infra.db.models.user import UserModel
from app.infra.security import decode_jwt
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.price_check_repository import PriceCheckRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.monitor_service import MonitorService

BASE_DIR = Path(__file__).resolve().parent
static_directory = BASE_DIR / "static"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

AUTH_COOKIE = "pm_access_token"
CSRF_COOKIE = "pm_csrf_token"

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
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    if await _current_user(request, users, settings):
        return _redirect("/monitors")
    return _render(request, "auth/login.html", {"title": "Вход"}, settings)


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
            "form": {"notification_channel": user.default_notification_channel or ""},
        },
        settings,
    )


@router.post("/monitors", response_class=HTMLResponse)
async def monitor_create(
    request: Request,
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


templates.env.filters["money"] = _format_money
templates.env.filters["dt"] = _format_dt
templates.env.filters["interval"] = _interval_label


class WebRedirect(Exception):
    def __init__(self, url: str):
        self.url = url


async def web_redirect_handler(request: Request, exc: WebRedirect) -> RedirectResponse:
    return _redirect(exc.url)

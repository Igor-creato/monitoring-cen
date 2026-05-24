from types import SimpleNamespace

import pytest

from app.domain.enums import UserRole
from app.infra.config import Settings
from app.web import router as web_router


@pytest.mark.asyncio
async def test_require_admin_allows_admin(monkeypatch) -> None:
    admin = SimpleNamespace(id=1, role=UserRole.ADMIN)

    async def fake_current_user(request, users, settings):
        return admin

    monkeypatch.setattr(web_router, "_current_user", fake_current_user)

    assert await web_router._require_admin(object(), object(), Settings()) is admin


@pytest.mark.asyncio
async def test_require_admin_redirects_regular_user(monkeypatch) -> None:
    user = SimpleNamespace(id=2, role=UserRole.USER)

    async def fake_current_user(request, users, settings):
        return user

    monkeypatch.setattr(web_router, "_current_user", fake_current_user)

    with pytest.raises(web_router.WebRedirect) as exc:
        await web_router._require_admin(object(), object(), Settings())

    assert exc.value.url == "/monitors"


@pytest.mark.asyncio
async def test_require_admin_redirects_anonymous(monkeypatch) -> None:
    async def fake_current_user(request, users, settings):
        return None

    monkeypatch.setattr(web_router, "_current_user", fake_current_user)

    with pytest.raises(web_router.WebRedirect) as exc:
        await web_router._require_admin(object(), object(), Settings())

    assert exc.value.url == "/login"

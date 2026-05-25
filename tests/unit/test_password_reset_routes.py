from app.api.deps import get_auth_service, get_settings
from app.infra.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


class FakePasswordResetService:
    def __init__(self) -> None:
        self.requested = []
        self.confirmed = []

    async def request_password_reset(self, email, base_url=None):
        self.requested.append({"email": email, "base_url": base_url})
        return "raw-token-for-reset"

    async def confirm_password_reset(self, token, password):
        self.confirmed.append({"token": token, "password": password})


def test_api_password_reset_request_returns_accepted() -> None:
    app = create_app()
    service = FakePasswordResetService()
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(jwt_secret_key="test-secret")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "user@example.com"},
        )

    assert response.status_code == 202
    assert service.requested == [{"email": "user@example.com", "base_url": None}]


def test_api_password_reset_confirm_returns_no_content() -> None:
    app = create_app()
    service = FakePasswordResetService()
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(jwt_secret_key="test-secret")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "raw-token-for-reset", "password": "new-password"},
        )

    assert response.status_code == 204
    assert service.confirmed == [{"token": "raw-token-for-reset", "password": "new-password"}]


def test_web_forgot_password_request_uses_request_origin_as_base_url() -> None:
    app = create_app()
    service = FakePasswordResetService()
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(jwt_secret_key="test-secret")

    with TestClient(app, base_url="https://prices.example.test") as client:
        page = client.get("/forgot-password")
        csrf = page.cookies["pm_csrf_token"]
        response = client.post(
            "/forgot-password",
            data={"email": "user@example.com", "csrf_token": csrf},
            follow_redirects=False,
        )

    assert response.status_code == 200
    assert service.requested == [
        {"email": "user@example.com", "base_url": "https://prices.example.test"}
    ]
    assert "Если такой email зарегистрирован" in response.text


def test_web_reset_password_confirm_uses_submitted_token() -> None:
    app = create_app()
    service = FakePasswordResetService()
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(jwt_secret_key="test-secret")

    with TestClient(app) as client:
        page = client.get("/reset-password?token=raw-token-for-reset")
        csrf = page.cookies["pm_csrf_token"]
        response = client.post(
            "/reset-password",
            data={
                "token": "raw-token-for-reset",
                "password": "new-password",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?reset=success"
    assert service.confirmed == [{"token": "raw-token-for-reset", "password": "new-password"}]

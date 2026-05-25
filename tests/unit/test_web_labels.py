import tomllib
from pathlib import Path
from types import SimpleNamespace

from app.domain.enums import (
    AvailabilityStatus,
    CheckStatus,
    Marketplace,
    MonitorStatus,
    NotificationStatus,
)
from app.web.router import templates


def test_renders_russian_labels_for_statuses_and_marketplaces() -> None:
    template = templates.env.from_string(
        "{{ monitor|monitor_status_label }}|"
        "{{ check|check_status_label }}|"
        "{{ availability|availability_label }}|"
        "{{ marketplace|marketplace_label }}"
    )

    rendered = template.render(
        monitor=MonitorStatus.ACTIVE,
        check=CheckStatus.NOT_MODIFIED,
        availability=AvailabilityStatus.IN_STOCK,
        marketplace=Marketplace.WILDBERRIES,
    )

    assert rendered == "Активен|Без изменений|В наличии|Wildberries"


def test_new_monitor_template_contains_marketplace_select() -> None:
    template_path = Path("backend/app/web/templates/monitors/new.html")
    template = template_path.read_text(encoding="utf-8")

    assert 'name="marketplace"' in template
    assert "Сейчас доступен мониторинг Wildberries." in template


def test_python_package_includes_web_static_assets() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    setuptools_config = pyproject["tool"]["setuptools"]

    assert setuptools_config["package-dir"][""] == "backend"
    assert setuptools_config["packages"]["find"]["where"] == ["backend"]
    assert "web/static/*" in setuptools_config["package-data"]["app"]
    assert "web/templates/**/*.html" in setuptools_config["package-data"]["app"]


def test_base_template_uses_proxy_safe_static_paths() -> None:
    template = Path("backend/app/web/templates/base.html").read_text(encoding="utf-8")

    assert "request.app.url_path_for('static'" in template
    assert "url_for('static'" not in template


def test_base_template_contains_visible_logout_button() -> None:
    template = Path("backend/app/web/templates/base.html").read_text(encoding="utf-8")

    assert 'action="/logout"' in template
    assert "Выйти" in template
    assert "logout-button" in template
    assert ">↗</button>" not in template


def test_login_template_links_to_forgot_password() -> None:
    template = Path("backend/app/web/templates/auth/login.html").read_text(encoding="utf-8")

    assert 'href="/forgot-password"' in template
    assert "Забыли пароль?" in template


def test_password_reset_templates_include_csrf_fields() -> None:
    forgot_template = Path("backend/app/web/templates/auth/forgot_password.html")
    reset_template = Path("backend/app/web/templates/auth/reset_password.html")

    assert 'name="csrf_token"' in forgot_template.read_text(encoding="utf-8")
    assert 'name="csrf_token"' in reset_template.read_text(encoding="utf-8")


def test_admin_runtime_and_notification_labels_are_russian() -> None:
    template = templates.env.from_string(
        "{{ setting.key|runtime_setting_label }}|"
        "{{ setting.source|runtime_setting_source_label }}|"
        "{{ provider|runtime_setting_value_label }}|"
        "{{ setting.updated_at|runtime_setting_updated_label }}|"
        "{{ status|notification_status_label }}|"
        "{{ error|runtime_settings_error_label }}"
    )

    rendered = template.render(
        setting=SimpleNamespace(
            key="apify_api_token",
            source="missing",
            updated_at=None,
        ),
        provider="wildberries_direct",
        status=NotificationStatus.FAILED,
        error="ADMIN_SECRETS_KEY is required for encrypted settings",
    )

    assert rendered == (
        "Токен API Apify|"
        "Не задано|"
        "Wildberries напрямую|"
        "Из .env или значения по умолчанию|"
        "Ошибка отправки|"
        "Для сохранения секретов задайте ADMIN_SECRETS_KEY"
    )


def test_admin_templates_do_not_show_raw_english_operational_labels() -> None:
    admin_templates = Path("backend/app/web/templates/admin")
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in admin_templates.glob("*.html")
    )

    forbidden = [
        "Parser errors",
        "Failed checks",
        "Runtime-настройки",
        "provider config",
        "env/default",
        "DB override",
        "User ID",
        "<th>User</th>",
        "<th>Monitor</th>",
        "pending</span>",
        "failed</span>",
        "none",
    ]

    for text in forbidden:
        assert text not in combined

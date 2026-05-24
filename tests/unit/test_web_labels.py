from pathlib import Path

from app.domain.enums import AvailabilityStatus, CheckStatus, Marketplace, MonitorStatus
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

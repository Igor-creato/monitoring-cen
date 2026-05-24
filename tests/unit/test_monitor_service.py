from types import SimpleNamespace

import pytest
from app.api.v1.schemas.monitor import MonitorCreateRequest
from app.domain.enums import Marketplace
from app.domain.exceptions import UnsupportedMarketplaceError
from app.services.monitor_service import MonitorService


class FakeMonitorRepository:
    def __init__(self) -> None:
        self.created_values: dict | None = None

    async def create(self, **values):
        self.created_values = values
        return SimpleNamespace(id=1, **values)


@pytest.mark.asyncio
async def test_create_monitor_accepts_matching_selected_marketplace() -> None:
    repository = FakeMonitorRepository()
    service = MonitorService(repository)
    payload = MonitorCreateRequest(
        url="https://www.wildberries.ru/catalog/987654321/detail.aspx?targetUrl=GP",
        marketplace=Marketplace.WILDBERRIES,
    )

    monitor = await service.create_monitor(42, payload)

    assert monitor.marketplace == Marketplace.WILDBERRIES
    assert monitor.url == "https://www.wildberries.ru/catalog/987654321/detail.aspx"
    assert repository.created_values["user_id"] == 42


@pytest.mark.asyncio
async def test_create_monitor_rejects_url_from_different_marketplace() -> None:
    service = MonitorService(FakeMonitorRepository())
    payload = MonitorCreateRequest(
        url="https://www.ozon.ru/product/apple-iphone-15-128gb-chernyy-123456789/",
        marketplace=Marketplace.WILDBERRIES,
    )

    with pytest.raises(
        UnsupportedMarketplaceError,
        match="Ссылка не относится к выбранному маркетплейсу",
    ):
        await service.create_monitor(42, payload)

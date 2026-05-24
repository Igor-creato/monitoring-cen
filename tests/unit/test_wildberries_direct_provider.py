from decimal import Decimal

import httpx
import pytest
from app.domain.enums import AvailabilityStatus, Marketplace
from app.product_fetching.providers import (
    WildberriesDirectProvider,
    WildberriesDirectProviderConfig,
)


def _provider(handler, **config) -> WildberriesDirectProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return WildberriesDirectProvider(
        http_client=client,
        config=WildberriesDirectProviderConfig(
            request_timeout_seconds=10,
            **config,
        ),
    )


def _product_payload(**overrides):
    product = {
        "id": 983268564,
        "name": "Стол маникюрный",
        "brand": "GARUN",
        "supplier": "GARUN Мебель",
        "totalQuantity": 3,
        "sizes": [
            {
                "price": {"product": 287700, "basic": 1400000},
                "stocks": [{"qty": 3}],
            }
        ],
    }
    product.update(overrides)
    return {"products": [product]}


@pytest.mark.asyncio
async def test_wildberries_direct_returns_snapshot_from_v4_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cards/v4/detail"
        assert request.url.params["nm"] == "983268564"
        assert request.url.params["dest"] == "-1257786"
        assert request.headers["origin"] == "https://www.wildberries.ru"
        assert request.headers["referer"].endswith("/catalog/983268564/detail.aspx")
        return httpx.Response(200, json=_product_payload(), request=request)

    snapshot = await _provider(handler).fetch_product(
        "https://wildberries.ru/catalog/983268564/detail.aspx?utm_source=share"
    )

    assert snapshot.success is True
    assert snapshot.normalized_url == "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    assert snapshot.marketplace == Marketplace.WILDBERRIES
    assert snapshot.title == "Стол маникюрный"
    assert snapshot.current_price == Decimal("2877")
    assert snapshot.old_price == Decimal("14000")
    assert snapshot.currency == "RUB"
    assert snapshot.availability == AvailabilityStatus.IN_STOCK
    assert snapshot.seller_name == "GARUN Мебель"
    assert snapshot.raw_payload["source"] == "cards_v4_detail"


@pytest.mark.asyncio
async def test_wildberries_direct_falls_back_to_v2_detail() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/cards/v4/detail":
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            json={"data": {"products": [_product_payload()["products"][0]]}},
            request=request,
        )

    snapshot = await _provider(handler).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is True
    assert paths == ["/cards/v4/detail", "/cards/v2/detail"]
    assert snapshot.raw_payload["source"] == "cards_v2_detail"


@pytest.mark.asyncio
async def test_wildberries_direct_falls_back_to_legacy_cards_detail() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path in {"/cards/v4/detail", "/cards/v2/detail"}:
            return httpx.Response(404, request=request)
        return httpx.Response(200, json=_product_payload(salePriceU=199900), request=request)

    snapshot = await _provider(handler).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is True
    assert paths == ["/cards/v4/detail", "/cards/v2/detail", "/cards/detail"]
    assert snapshot.current_price == Decimal("1999")
    assert snapshot.raw_payload["source"] == "cards_detail"


@pytest.mark.asyncio
async def test_wildberries_direct_falls_back_to_basket_card_json() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if request.url.host == "card.wb.ru":
            return httpx.Response(404, request=request)
        if request.url.host == "basket-01.wbbasket.ru":
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            json={
                "nm_id": 983268564,
                "imt_name": "Стол из card.json",
                "brand": "GARUN",
            },
            request=request,
        )

    snapshot = await _provider(handler, basket_max_host=2).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is True
    assert snapshot.title == "Стол из card.json"
    assert snapshot.current_price is None
    assert snapshot.seller_name == "GARUN"
    assert snapshot.image_url == (
        "https://basket-02.wbbasket.ru/vol9832/part983268/983268564/images/big/1.webp"
    )
    assert snapshot.raw_payload["source"] == "basket_card_json"
    assert any("basket-02.wbbasket.ru/vol9832/part983268/983268564" in url for url in urls)


@pytest.mark.asyncio
async def test_wildberries_direct_allows_product_without_price() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_product_payload(sizes=[], totalQuantity=0),
            request=request,
        )

    snapshot = await _provider(handler).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is True
    assert snapshot.current_price is None
    assert snapshot.availability == AvailabilityStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_wildberries_direct_maps_429_to_blocked_failure_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Too many requests"}, request=request)

    snapshot = await _provider(handler).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is False
    assert snapshot.error_code == "provider_blocked"
    assert snapshot.raw_payload["attempts"][0]["status_code"] == 429


@pytest.mark.asyncio
async def test_wildberries_direct_accepts_product_payload_with_x_pow_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-pow": "status=invalid"},
            json=_product_payload(salePriceU=199900),
            request=request,
        )

    snapshot = await _provider(handler).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is True
    assert snapshot.current_price == Decimal("1999")


@pytest.mark.asyncio
async def test_wildberries_direct_maps_x_pow_without_product_to_blocked_failure_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-pow": "required"},
            json={"products": []},
            request=request,
        )

    snapshot = await _provider(handler).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is False
    assert snapshot.error_code == "provider_blocked"


@pytest.mark.asyncio
async def test_wildberries_direct_maps_empty_fallbacks_to_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    snapshot = await _provider(handler, basket_max_host=2).fetch_product(
        "https://www.wildberries.ru/catalog/983268564/detail.aspx"
    )

    assert snapshot.success is False
    assert snapshot.error_code == "product_not_found"
    assert [item["source"] for item in snapshot.raw_payload["attempts"]] == [
        "cards_v4_detail",
        "cards_v2_detail",
        "cards_detail",
        "basket_card_json",
        "basket_card_json",
    ]

from decimal import Decimal

import httpx
import pytest
from app.domain.enums import AvailabilityStatus, Marketplace
from app.infra.config import Settings
from app.product_fetching.exceptions import ProviderConfigurationError, ProviderTimeoutError
from app.product_fetching.factory import ProductProviderFactory
from app.product_fetching.providers import MockProvider, WildberriesDirectProvider
from app.product_fetching.retry import ExponentialBackoffRetryPolicy


@pytest.mark.asyncio
async def test_mock_provider_returns_provider_neutral_snapshot() -> None:
    normalized_url = "https://www.ozon.ru/product/apple-iphone-15-123456789/"
    provider = MockProvider(
        fixtures={
            normalized_url: {
                "title": "Apple iPhone 15",
                "price": "79 990 ₽",
                "oldPrice": "89 990 ₽",
                "inStock": True,
                "sellerName": "Ozon",
                "imageUrl": "https://cdn.example.test/iphone.jpg",
            },
        },
    )

    snapshot = await provider.fetch_product(
        "https://ozon.ru/product/apple-iphone-15-123456789/?utm_source=share",
    )

    assert snapshot.success is True
    assert snapshot.normalized_url == normalized_url
    assert snapshot.marketplace == Marketplace.OZON
    assert snapshot.title == "Apple iPhone 15"
    assert snapshot.current_price == Decimal("79990")
    assert snapshot.old_price == Decimal("89990")
    assert snapshot.currency == "RUB"
    assert snapshot.availability == AvailabilityStatus.IN_STOCK
    assert snapshot.seller_name == "Ozon"
    assert snapshot.error_code is None


@pytest.mark.asyncio
async def test_provider_returns_failure_snapshot_for_unsupported_url() -> None:
    snapshot = await MockProvider().fetch_product("https://example.com/product/123")

    assert snapshot.success is False
    assert snapshot.marketplace == Marketplace.UNKNOWN
    assert snapshot.error_code == "unsupported_product_url"
    assert snapshot.error_message == "Marketplace domain is not supported"


@pytest.mark.asyncio
async def test_retry_policy_retries_retryable_product_fetch_errors() -> None:
    calls = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProviderTimeoutError("temporary timeout")
        return "ok"

    policy = ExponentialBackoffRetryPolicy(
        max_attempts=2,
        base_delay_seconds=0,
        max_delay_seconds=0,
        jitter_ratio=0,
        sleep=sleep,
    )

    assert await policy.run(operation, operation_name="test") == "ok"
    assert calls == 2
    assert delays == [0]


@pytest.mark.asyncio
async def test_factory_requires_apify_configuration() -> None:
    settings = Settings(
        _env_file=None,
        product_fetch_provider="apify",
        apify_api_token=None,
        apify_actor_id="actor",
    )

    async with httpx.AsyncClient() as http_client:
        factory = ProductProviderFactory(http_client=http_client, settings=settings)

        with pytest.raises(ProviderConfigurationError, match="APIFY_API_TOKEN is required"):
            factory.create()


@pytest.mark.asyncio
async def test_factory_creates_wildberries_direct_without_apify_configuration() -> None:
    settings = Settings(
        _env_file=None,
        product_fetch_provider="wildberries_direct",
        apify_api_token=None,
        apify_actor_id=None,
        wildberries_proxy_url="http://proxy.example.test:8080",
    )

    async with httpx.AsyncClient() as http_client:
        factory = ProductProviderFactory(http_client=http_client, settings=settings)

        provider = factory.create()

    assert isinstance(provider, WildberriesDirectProvider)

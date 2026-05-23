import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from app.domain.enums import AvailabilityStatus, Marketplace
from app.product_fetching.providers import ApifyProvider, ApifyProviderConfig
from app.product_fetching.retry import ExponentialBackoffRetryPolicy

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "apify"


def _fixture(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _provider_for_payload(payload: object) -> ApifyProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        request_payload = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer test-token"
        assert request_payload["maxItems"] == 1
        assert request.url.path == "/v2/acts/owner~wildberries/run-sync-get-dataset-items"
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ApifyProvider(
        http_client=client,
        config=ApifyProviderConfig(
            api_token="test-token",
            actor_id="owner~wildberries",
            base_url="https://api.apify.test",
            request_timeout_seconds=10,
        ),
    )


@pytest.mark.asyncio
async def test_apify_wildberries_returns_snapshot_from_found_fixture() -> None:
    provider = _provider_for_payload(_fixture("wildberries_found.json"))

    snapshot = await provider.fetch_product(
        "https://wildberries.ru/catalog/178123456/detail.aspx?utm_source=share",
    )

    assert snapshot.success is True
    assert snapshot.normalized_url == "https://www.wildberries.ru/catalog/178123456/detail.aspx"
    assert snapshot.marketplace == Marketplace.WILDBERRIES
    assert snapshot.title == "Смартфон Example X 256 ГБ"
    assert snapshot.current_price == Decimal("79990")
    assert snapshot.old_price == Decimal("89990")
    assert snapshot.currency == "RUB"
    assert snapshot.availability == AvailabilityStatus.IN_STOCK
    assert snapshot.seller_name == "Example Store"
    assert snapshot.image_url == "https://images.wbstatic.net/example-x.jpg"
    assert snapshot.raw_payload["request"]["startUrls"][0]["url"] == snapshot.normalized_url
    assert snapshot.raw_payload["response"] == _fixture("wildberries_found.json")


@pytest.mark.asyncio
async def test_apify_wildberries_returns_snapshot_for_unavailable_product() -> None:
    provider = _provider_for_payload(_fixture("wildberries_unavailable.json"))

    snapshot = await provider.fetch_product(
        "https://www.wildberries.ru/catalog/178123457/detail.aspx",
    )

    assert snapshot.success is True
    assert snapshot.title == "Наушники Example Buds"
    assert snapshot.current_price is None
    assert snapshot.currency == "RUB"
    assert snapshot.availability == AvailabilityStatus.UNAVAILABLE
    assert snapshot.raw_payload["item"]["product"]["availability"] == "unavailable"


@pytest.mark.asyncio
async def test_apify_wildberries_returns_page_changed_failure_snapshot() -> None:
    provider = _provider_for_payload(_fixture("wildberries_page_changed.json"))

    snapshot = await provider.fetch_product(
        "https://www.wildberries.ru/catalog/178123458/detail.aspx",
    )

    assert snapshot.success is False
    assert snapshot.error_code == "page_structure_changed"
    assert snapshot.raw_payload["item"]["payloadVersion"] == "unknown-layout-v99"


@pytest.mark.asyncio
async def test_apify_wildberries_handles_target_antibot_403() -> None:
    provider = _provider_for_payload(
        [
            {
                "url": "https://www.wildberries.ru/catalog/178123459/detail.aspx",
                "httpStatus": 403,
                "errorMessage": "Access denied by anti-bot protection",
            },
        ],
    )

    snapshot = await provider.fetch_product(
        "https://www.wildberries.ru/catalog/178123459/detail.aspx",
    )

    assert snapshot.success is False
    assert snapshot.error_code == "provider_blocked"
    assert snapshot.raw_payload["item"]["httpStatus"] == 403


@pytest.mark.asyncio
async def test_apify_wildberries_retries_provider_429() -> None:
    calls = 0

    async def sleep(delay: float) -> None:
        assert delay == 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            json={"error": {"type": "rate-limit-exceeded", "message": "Too many requests"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ApifyProvider(
        http_client=client,
        config=ApifyProviderConfig(
            api_token="test-token",
            actor_id="owner~wildberries",
            base_url="https://api.apify.test",
            request_timeout_seconds=10,
        ),
        retry_policy=ExponentialBackoffRetryPolicy(
            max_attempts=2,
            base_delay_seconds=0,
            max_delay_seconds=0,
            jitter_ratio=0,
            sleep=sleep,
        ),
    )

    snapshot = await provider.fetch_product(
        "https://www.wildberries.ru/catalog/178123460/detail.aspx",
    )

    assert calls == 2
    assert snapshot.success is False
    assert snapshot.error_code == "provider_rate_limited"
    assert snapshot.raw_payload["status_code"] == 429


@pytest.mark.asyncio
async def test_apify_wildberries_handles_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ApifyProvider(
        http_client=client,
        config=ApifyProviderConfig(
            api_token="test-token",
            actor_id="owner~wildberries",
            base_url="https://api.apify.test",
            request_timeout_seconds=10,
        ),
    )

    snapshot = await provider.fetch_product(
        "https://www.wildberries.ru/catalog/178123461/detail.aspx",
    )

    assert snapshot.success is False
    assert snapshot.error_code == "provider_timeout"

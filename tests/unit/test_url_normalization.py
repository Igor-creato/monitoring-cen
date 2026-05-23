import pytest
from app.domain.enums import Marketplace
from app.domain.url_normalization import normalize_product_url


@pytest.mark.parametrize(
    ("url", "marketplace", "normalized_url"),
    [
        (
            "https://www.ozon.ru/product/apple-iphone-15-128gb-chernyy-123456789/"
            "?utm_source=share&from=search&src=ios&sku=123#reviews",
            Marketplace.OZON,
            "https://www.ozon.ru/product/apple-iphone-15-128gb-chernyy-123456789/",
        ),
        (
            "http://ozon.ru/product/noutbuk-huawei-matebook-987654321?advert=abc",
            Marketplace.OZON,
            "https://www.ozon.ru/product/noutbuk-huawei-matebook-987654321/",
        ),
        (
            "https://wildberries.ru/catalog/987654321/detail.aspx"
            "?targetUrl=GP&utm_medium=cpc&from=search",
            Marketplace.WILDBERRIES,
            "https://www.wildberries.ru/catalog/987654321/detail.aspx",
        ),
        (
            "https://m.wildberries.ru/catalog/987654321/detail.aspx?size=123456789",
            Marketplace.WILDBERRIES,
            "https://www.wildberries.ru/catalog/987654321/detail.aspx",
        ),
        (
            "https://market.yandex.ru/product--smartfon-apple-iphone-15/1722193751"
            "?sku=102875219&uniqueId=924574&hid=91491&utm_source=yandex",
            Marketplace.YANDEX_MARKET,
            "https://market.yandex.ru/product--smartfon-apple-iphone-15/1722193751",
        ),
        (
            "https://www.market.yandex.ru/product--kholodilnik-atlant/100500/?clid=703",
            Marketplace.YANDEX_MARKET,
            "https://market.yandex.ru/product--kholodilnik-atlant/100500",
        ),
    ],
)
def test_normalizes_supported_product_card_urls(
    url: str,
    marketplace: Marketplace,
    normalized_url: str,
) -> None:
    result = normalize_product_url(url)

    assert result.original_url == url
    assert result.normalized_url == normalized_url
    assert result.marketplace == marketplace
    assert result.is_supported is True
    assert result.reason_if_invalid is None


@pytest.mark.parametrize(
    ("url", "marketplace", "reason"),
    [
        (
            "https://www.ozon.ru/search/?text=iphone",
            Marketplace.OZON,
            "URL is not a supported product card",
        ),
        (
            "https://www.ozon.ru/category/smartfony-15502/",
            Marketplace.OZON,
            "URL is not a supported product card",
        ),
        (
            "https://www.ozon.ru/redirect?to=https%3A%2F%2Fexample.com",
            Marketplace.OZON,
            "URL is not a supported product card",
        ),
        (
            "https://www.wildberries.ru/catalog/elektronika/smartfony",
            Marketplace.WILDBERRIES,
            "URL is not a supported product card",
        ),
        (
            "https://www.wildberries.ru/catalog/987654321",
            Marketplace.WILDBERRIES,
            "URL is not a supported product card",
        ),
        (
            "https://market.yandex.ru/catalog--smartfony/16814639/list",
            Marketplace.YANDEX_MARKET,
            "URL is not a supported product card",
        ),
        (
            "https://market.yandex.ru/redirect?url=https%3A%2F%2Fexample.com",
            Marketplace.YANDEX_MARKET,
            "URL is not a supported product card",
        ),
        (
            "https://example.com/product/123456",
            Marketplace.UNKNOWN,
            "Marketplace domain is not supported",
        ),
        (
            "https://wb.ru/catalog/987654321/detail.aspx",
            Marketplace.UNKNOWN,
            "Marketplace domain is not supported",
        ),
        (
            "ftp://www.ozon.ru/product/foo-123456",
            Marketplace.UNKNOWN,
            "URL scheme must be http or https",
        ),
        (
            "https://ozon.ru.evil.example/product/foo-123456",
            Marketplace.UNKNOWN,
            "Marketplace domain is not supported",
        ),
        (
            "https://user:secret@www.ozon.ru/product/foo-123456",
            Marketplace.UNKNOWN,
            "URL must not contain credentials",
        ),
    ],
)
def test_rejects_non_product_or_unsupported_urls(
    url: str,
    marketplace: Marketplace,
    reason: str,
) -> None:
    result = normalize_product_url(url)

    assert result.original_url == url
    assert result.normalized_url is None
    assert result.marketplace == marketplace
    assert result.is_supported is False
    assert result.reason_if_invalid == reason


def test_strips_surrounding_spaces_before_parsing() -> None:
    result = normalize_product_url(
        "  https://www.ozon.ru/product/apple-iphone-15-123456789/?utm_source=x  "
    )

    assert result.original_url == "https://www.ozon.ru/product/apple-iphone-15-123456789/?utm_source=x"
    assert result.normalized_url == "https://www.ozon.ru/product/apple-iphone-15-123456789/"

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx

from app.domain.enums import AvailabilityStatus, Marketplace
from app.product_fetching.base import AbstractProductProvider
from app.product_fetching.exceptions import (
    PageStructureChangedError,
    ProductNotFoundError,
    ProviderBlockedError,
    ProviderPayloadError,
    ProviderRequestError,
    ProviderTimeoutError,
    UnsupportedProductUrlError,
)
from app.product_fetching.models import ProductSnapshot
from app.product_fetching.providers.wildberries.mapping import is_antibot_payload
from app.product_fetching.retry import RetryPolicy


@dataclass(frozen=True, slots=True)
class WildberriesDirectProviderConfig:
    dest: str = "-1257786"
    request_timeout_seconds: float = 60
    basket_max_host: int = 20
    proxy_url: str | None = None


@dataclass(frozen=True, slots=True)
class WildberriesDirectResult:
    source: str
    basket_host: str | None
    payload: Mapping[str, Any]
    attempts: tuple[dict[str, Any], ...]


class WildberriesDirectProvider(AbstractProductProvider):
    name = "wildberries_direct"
    marketplace = Marketplace.WILDBERRIES
    card_base_url = "https://card.wb.ru"

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        config: WildberriesDirectProviderConfig,
        retry_policy: RetryPolicy | None = None,
    ):
        super().__init__(retry_policy=retry_policy)
        self.http_client = http_client
        self.config = config

    async def _fetch_normalized(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
    ) -> ProductSnapshot:
        if marketplace != self.marketplace:
            raise UnsupportedProductUrlError(
                "Wildberries direct provider supports only Wildberries product URLs",
                provider_name=self.name,
            )

        nm_id = _wildberries_nm_id(normalized_url)
        result = await self._fetch_payload(nm_id)
        product = _extract_product(result.payload)
        values = _map_product(product, nm_id=nm_id, basket_host=result.basket_host)

        if not _has_product_signal(values):
            raise PageStructureChangedError(
                "Wildberries direct response does not contain recognizable product fields",
                provider_name=self.name,
                raw_payload={"source": result.source, "response": dict(result.payload)},
            )

        return self._success_snapshot(
            normalized_url=normalized_url,
            marketplace=marketplace,
            raw_payload={
                "provider": self.name,
                "marketplace": self.marketplace,
                "nm_id": nm_id,
                "source": result.source,
                "basket_host": result.basket_host,
                "attempts": result.attempts,
                "response": result.payload,
                "product": product,
            },
            **values,
        )

    async def _fetch_payload(self, nm_id: str) -> WildberriesDirectResult:
        attempts: list[dict[str, Any]] = []
        headers = _headers(nm_id)

        for source, path in (
            ("cards_v4_detail", "/cards/v4/detail"),
            ("cards_v2_detail", "/cards/v2/detail"),
            ("cards_detail", "/cards/detail"),
        ):
            url = f"{self.card_base_url}{path}"
            params = {
                "appType": "1",
                "curr": "rub",
                "dest": self.config.dest,
                "spp": "30",
                "nm": nm_id,
            }
            response = await self._get(url, headers=headers, params=params)
            attempt = _attempt_record(source, str(response.url), response)
            attempts.append(attempt)

            if self._is_blocked(response):
                raise ProviderBlockedError(
                    f"Wildberries blocked direct request: HTTP {response.status_code}",
                    provider_name=self.name,
                    raw_payload={"attempts": attempts},
                )
            if response.status_code in {408, 504}:
                raise ProviderTimeoutError(
                    f"Wildberries direct request timed out: HTTP {response.status_code}",
                    provider_name=self.name,
                    raw_payload={"attempts": attempts},
                )
            if response.status_code >= 500:
                raise ProviderRequestError(
                    f"Wildberries direct request failed: HTTP {response.status_code}",
                    provider_name=self.name,
                    raw_payload={"attempts": attempts},
                )
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                raise ProviderRequestError(
                    f"Wildberries direct request failed: HTTP {response.status_code}",
                    retryable=False,
                    provider_name=self.name,
                    raw_payload={"attempts": attempts},
                )

            payload = self._decode_json(response, attempts)
            if is_antibot_payload(payload):
                raise ProviderBlockedError(
                    "Wildberries direct response looks like anti-bot protection",
                    provider_name=self.name,
                    raw_payload={"attempts": attempts, "response": payload},
                )
            if _extract_product(payload) is not None:
                return WildberriesDirectResult(
                    source=source,
                    basket_host=None,
                    payload=payload,
                    attempts=tuple(attempts),
                )

        basket_result = await self._fetch_basket_payload(nm_id, headers, attempts)
        if basket_result is not None:
            return basket_result

        raise ProductNotFoundError(
            "Wildberries product was not found by direct endpoints",
            provider_name=self.name,
            raw_payload={"attempts": attempts},
        )

    async def _fetch_basket_payload(
        self,
        nm_id: str,
        headers: Mapping[str, str],
        attempts: list[dict[str, Any]],
    ) -> WildberriesDirectResult | None:
        vol = int(nm_id) // 100_000
        part = int(nm_id) // 1_000

        for host_number in range(1, self.config.basket_max_host + 1):
            basket_host = f"basket-{host_number:02d}.wbbasket.ru"
            url = f"https://{basket_host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
            response = await self._get(url, headers=headers)
            attempts.append(_attempt_record("basket_card_json", str(response.url), response))

            if self._is_blocked(response):
                raise ProviderBlockedError(
                    f"Wildberries basket blocked direct request: HTTP {response.status_code}",
                    provider_name=self.name,
                    raw_payload={"attempts": attempts},
                )
            if response.status_code == 404:
                continue
            if response.status_code >= 500:
                continue
            if response.status_code >= 400:
                raise ProviderRequestError(
                    f"Wildberries basket request failed: HTTP {response.status_code}",
                    retryable=False,
                    provider_name=self.name,
                    raw_payload={"attempts": attempts},
                )

            payload = self._decode_json(response, attempts)
            if is_antibot_payload(payload):
                raise ProviderBlockedError(
                    "Wildberries basket response looks like anti-bot protection",
                    provider_name=self.name,
                    raw_payload={"attempts": attempts, "response": payload},
                )
            if _extract_product(payload) is not None:
                return WildberriesDirectResult(
                    source="basket_card_json",
                    basket_host=basket_host,
                    payload=payload,
                    attempts=tuple(attempts),
                )
        return None

    async def _get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            if self.config.proxy_url:
                async with httpx.AsyncClient(
                    proxy=self.config.proxy_url,
                    timeout=self.config.request_timeout_seconds,
                    follow_redirects=True,
                ) as proxy_client:
                    return await proxy_client.get(url, params=params, headers=headers)
            return await self.http_client.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.request_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                "Wildberries direct request timed out",
                provider_name=self.name,
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderRequestError(
                "Wildberries direct transport error",
                provider_name=self.name,
            ) from exc

    def _decode_json(
        self,
        response: httpx.Response,
        attempts: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderPayloadError(
                "Wildberries returned non-JSON response",
                provider_name=self.name,
                raw_payload={
                    "attempts": list(attempts),
                    "status_code": response.status_code,
                    "text": response.text[:1000],
                },
            ) from exc
        if not isinstance(payload, Mapping):
            raise ProviderPayloadError(
                "Wildberries returned JSON response with unexpected root type",
                provider_name=self.name,
                raw_payload={"attempts": list(attempts), "response": payload},
            )
        return payload

    @staticmethod
    def _is_blocked(response: httpx.Response) -> bool:
        if response.status_code in {403, 429}:
            return True
        return any(header.lower() == "x-pow" for header in response.headers)


def _headers(nm_id: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.wildberries.ru",
        "Referer": f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _attempt_record(source: str, url: str, response: httpx.Response) -> dict[str, Any]:
    return {
        "source": source,
        "url": url,
        "status_code": response.status_code,
        "headers": {
            key: value
            for key, value in response.headers.items()
            if key.lower() in {"content-type", "x-pow", "x-captcha-id"}
        },
    }


def _extract_product(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for value in (
        payload.get("products"),
        _value_at_path(payload, ("data", "products")),
        _value_at_path(payload, ("data", "product")),
        payload.get("product"),
    ):
        if isinstance(value, Sequence) and not isinstance(value, str):
            first = next((item for item in value if isinstance(item, Mapping)), None)
            if isinstance(first, Mapping):
                return first
        if isinstance(value, Mapping):
            return value

    if _looks_like_basket_card(payload):
        return payload
    return None


def _map_product(
    product: Mapping[str, Any],
    *,
    nm_id: str,
    basket_host: str | None,
) -> dict[str, Any]:
    current_price = _first_price(
        product,
        (
            (("salePriceU",), True),
            (("sale_price_u",), True),
            (("salePrice",), False),
            (("sale_price",), False),
            (("salePriceRub",), False),
            (("sale_price_rub",), False),
            (("priceU",), True),
            (("price", "salePriceU"), True),
            (("price", "salePrice"), False),
            (("price", "current"), False),
            (("currentPrice",), False),
            (("current_price",), False),
            (("finalPriceRub",), False),
            (("finalPrice",), False),
            (("sizes", "*", "price", "product"), True),
            (("sizes", "*", "price", "sale"), True),
            (("sizes", "*", "price", "total"), True),
        ),
    )
    old_price = _first_price(
        product,
        (
            (("priceU",), True),
            (("retailPriceU",), True),
            (("oldPriceU",), True),
            (("old_price_u",), True),
            (("priceRub",), False),
            (("retailPriceRub",), False),
            (("oldPriceRub",), False),
            (("old_price_rub",), False),
            (("retailPrice",), False),
            (("oldPrice",), False),
            (("old_price",), False),
            (("price", "basic"), True),
            (("price", "old"), False),
            (("sizes", "*", "price", "basic"), True),
        ),
    )
    image_url = _first_image(product)
    if image_url is None and basket_host:
        image_url = _basket_image_url(nm_id, basket_host)

    return {
        "title": _first_text(
            product,
            (
                ("name",),
                ("title",),
                ("goodsName",),
                ("productName",),
                ("imt_name",),
            ),
        ),
        "current_price": current_price,
        "old_price": old_price,
        "currency": _currency(product, current_price),
        "availability": _availability(product),
        "seller_name": _first_text(
            product,
            (
                ("supplier", "name"),
                ("supplier",),
                ("supplierName",),
                ("seller", "name"),
                ("seller",),
                ("sellerName",),
                ("brand",),
                ("vendor",),
            ),
        ),
        "image_url": image_url,
    }


def _availability(product: Mapping[str, Any]) -> AvailabilityStatus:
    quantity = _total_quantity(product)
    if quantity is not None:
        return AvailabilityStatus.IN_STOCK if quantity > 0 else AvailabilityStatus.UNAVAILABLE

    value = _first_value(
        product,
        (
            ("availability",),
            ("availabilityStatus",),
            ("status",),
            ("inStock",),
            ("isAvailable",),
            ("available",),
            ("stock",),
            ("quantity",),
        ),
    )
    if isinstance(value, bool):
        return AvailabilityStatus.IN_STOCK if value else AvailabilityStatus.UNAVAILABLE
    parsed_quantity = _parse_decimal(value)
    if parsed_quantity is not None:
        if parsed_quantity > 0:
            return AvailabilityStatus.IN_STOCK
        return AvailabilityStatus.UNAVAILABLE
    if value is None:
        return AvailabilityStatus.UNKNOWN

    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"true", "available", "in_stock", "instock", "yes"}:
        return AvailabilityStatus.IN_STOCK
    if text in {"false", "unavailable", "out_of_stock", "outofstock", "sold_out", "no"}:
        return AvailabilityStatus.UNAVAILABLE
    if text in {"preorder", "pre_order"}:
        return AvailabilityStatus.PREORDER
    return AvailabilityStatus.UNKNOWN


def _total_quantity(product: Mapping[str, Any]) -> int | None:
    value = _first_value(product, (("totalQuantity",), ("total_quantity",)))
    quantity = _parse_int(value)
    if quantity is not None:
        return quantity

    total = 0
    found = False
    sizes = product.get("sizes")
    if not isinstance(sizes, Sequence) or isinstance(sizes, str):
        return None
    for size in sizes:
        if not isinstance(size, Mapping):
            continue
        stocks = size.get("stocks")
        if isinstance(stocks, Sequence) and not isinstance(stocks, str):
            for stock in stocks:
                if not isinstance(stock, Mapping):
                    continue
                stock_quantity = _parse_int(
                    _first_value(stock, (("qty",), ("quantity",), ("stock",)))
                )
                if stock_quantity is not None:
                    total += stock_quantity
                    found = True
        size_quantity = _parse_int(_first_value(size, (("qty",), ("quantity",), ("stock",))))
        if size_quantity is not None:
            total += size_quantity
            found = True
    return total if found else None


def _currency(product: Mapping[str, Any], current_price: Decimal | None) -> str | None:
    value = _first_value(
        product,
        (("currency",), ("currencyCode",), ("currency_code",), ("price", "currency")),
    )
    if value is None and current_price is not None:
        return "RUB"
    if value is None:
        return None
    text = str(value).strip().upper()
    return {"₽": "RUB", "Р": "RUB", "РУБ": "RUB", "RUR": "RUB"}.get(text, text)


def _first_text(product: Mapping[str, Any], paths: Sequence[tuple[str, ...]]) -> str | None:
    value = _first_value(product, paths)
    if isinstance(value, Mapping):
        value = _first_value(value, (("name",), ("title",), ("value",), ("text",)))
    if value is None:
        return None
    return str(value).strip() or None


def _first_image(product: Mapping[str, Any]) -> str | None:
    value = _first_value(
        product,
        (
            ("image",),
            ("imageUrl",),
            ("image_url",),
            ("mainImage",),
            ("thumbnail",),
            ("images",),
            ("photos",),
        ),
    )
    if isinstance(value, Sequence) and not isinstance(value, str):
        value = next((item for item in value if item), None)
    if isinstance(value, Mapping):
        value = _first_value(value, (("url",), ("src",), ("big",), ("c246x328",)))
    if value is None:
        return None
    return str(value).strip() or None


def _first_price(
    product: Mapping[str, Any],
    paths: Sequence[tuple[tuple[str, ...], bool]],
) -> Decimal | None:
    for path, divide_by_100 in paths:
        value = _first_value(product, (path,))
        price = _parse_decimal(value)
        if price is not None:
            return price / Decimal("100") if divide_by_100 else price
    return None


def _first_value(product: Mapping[str, Any], paths: Sequence[tuple[str, ...]]) -> Any:
    for path in paths:
        values = _values_at_path(product, path)
        for value in values:
            if value not in (None, "", [], {}):
                return value
    return None


def _values_at_path(current: Any, path: tuple[str, ...]) -> list[Any]:
    if not path:
        return [current]
    key, *rest = path
    remaining = tuple(rest)
    if key == "*":
        if not isinstance(current, Sequence) or isinstance(current, str):
            return []
        values: list[Any] = []
        for item in current:
            values.extend(_values_at_path(item, remaining))
        return values
    if not isinstance(current, Mapping) or key not in current:
        return []
    return _values_at_path(current[key], remaining)


def _value_at_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return _parse_decimal(_first_value(value, (("amount",), ("value",), ("price",))))

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\xa0", " ").replace(" ", "")
    text = re.sub(r"[^0-9,.\-]", "", text)
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    elif "," in text and "." in text:
        text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_int(value: Any) -> int | None:
    decimal = _parse_decimal(value)
    if decimal is None:
        return None
    return int(decimal)


def _has_product_signal(values: Mapping[str, Any]) -> bool:
    return bool(
        values.get("title")
        or values.get("current_price") is not None
        or values.get("availability") != AvailabilityStatus.UNKNOWN
    )


def _looks_like_basket_card(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in ("nm_id", "imt_name", "vendor_code", "description"))


def _basket_image_url(nm_id: str, basket_host: str) -> str:
    vol = int(nm_id) // 100_000
    part = int(nm_id) // 1_000
    return f"https://{basket_host}/vol{vol}/part{part}/{nm_id}/images/big/1.webp"


def _wildberries_nm_id(normalized_url: str) -> str:
    path_segments = tuple(
        segment for segment in urlparse(normalized_url).path.split("/") if segment
    )
    if (
        len(path_segments) >= 2
        and path_segments[0].lower() == "catalog"
        and path_segments[1].isdigit()
    ):
        return path_segments[1]
    raise PageStructureChangedError(
        "Wildberries normalized URL does not contain a product id",
        raw_payload={"normalized_url": normalized_url},
    )

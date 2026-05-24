import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from app.domain.enums import AvailabilityStatus
from app.product_fetching.exceptions import PageStructureChangedError

Path = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FieldSelector:
    paths: tuple[Path, ...]


PRODUCT_CONTAINER_PATHS: tuple[Path, ...] = (
    ("product",),
    ("productData",),
    ("data", "product"),
    ("result", "product"),
    ("item",),
    ("pageFunctionResult",),
)

ERROR_STATUS_SELECTOR = FieldSelector(
    (
        ("httpStatus",),
        ("httpStatusCode",),
        ("statusCode",),
        ("response", "statusCode"),
        ("error", "statusCode"),
        ("errorInfo", "statusCode"),
    ),
)
ERROR_CODE_SELECTOR = FieldSelector(
    (
        ("errorCode",),
        ("error_code",),
        ("error", "type"),
        ("error", "code"),
        ("errorInfo", "type"),
        ("errorInfo", "code"),
    ),
)
ERROR_MESSAGE_SELECTOR = FieldSelector(
    (
        ("errorMessage",),
        ("error_message",),
        ("message",),
        ("error", "message"),
        ("errorInfo", "message"),
    ),
)

TITLE_SELECTOR = FieldSelector(
    (
        ("title",),
        ("name",),
        ("productName",),
        ("goodsName",),
        ("card", "name"),
    ),
)
CURRENT_PRICE_SELECTOR = FieldSelector(
    (
        ("salePriceU",),
        ("sale_price_u",),
        ("salePriceRub",),
        ("sale_price_rub",),
        ("salePrice",),
        ("sale_price",),
        ("priceU",),
        ("price", "salePriceU"),
        ("price", "salePriceRub"),
        ("price", "salePrice"),
        ("price", "current"),
        ("currentPrice",),
        ("current_price",),
        ("finalPriceRub",),
        ("finalPrice",),
    ),
)
OLD_PRICE_SELECTOR = FieldSelector(
    (
        ("priceU",),
        ("retailPriceU",),
        ("oldPriceU",),
        ("old_price_u",),
        ("priceRub",),
        ("retailPriceRub",),
        ("oldPriceRub",),
        ("old_price_rub",),
        ("retailPrice",),
        ("oldPrice",),
        ("old_price",),
        ("price", "oldPriceU"),
        ("price", "oldPriceRub"),
        ("price", "old"),
    ),
)
CURRENCY_SELECTOR = FieldSelector(
    (
        ("currency",),
        ("currencyCode",),
        ("currency_code",),
        ("price", "currency"),
    ),
)
AVAILABILITY_SELECTOR = FieldSelector(
    (
        ("availability",),
        ("availabilityStatus",),
        ("status",),
        ("inStock",),
        ("isAvailable",),
        ("available",),
        ("stock",),
        ("quantity",),
        ("totalQuantity",),
        ("total_quantity",),
        ("isSoldOut",),
    ),
)
SELLER_SELECTOR = FieldSelector(
    (
        ("seller", "name"),
        ("supplier", "name"),
        ("seller",),
        ("supplier",),
        ("sellerName",),
        ("supplierName",),
        ("brand",),
        ("vendor",),
    ),
)
IMAGE_SELECTOR = FieldSelector(
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

ANTI_BOT_MARKERS = (
    "captcha",
    "robot",
    "anti-bot",
    "antibot",
    "access denied",
    "forbidden",
    "too many requests",
    "429",
)
NOT_FOUND_MARKERS = (
    "not_found",
    "not found",
    "404",
    "deleted",
    "removed",
    "товар не найден",
)


def build_apify_input(normalized_url: str) -> dict[str, Any]:
    nm_id = _wildberries_nm_id(normalized_url)
    return {
        "nmIds": [nm_id],
        "maxItems": 1,
        "proxyConfiguration": {"useApifyProxy": False},
    }


def map_product_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    current_price = _first_price(payload, CURRENT_PRICE_SELECTOR)
    availability = _extract_availability(payload)
    values = {
        "title": _first_text(payload, TITLE_SELECTOR),
        "current_price": current_price,
        "old_price": _first_price(payload, OLD_PRICE_SELECTOR),
        "currency": _extract_currency(payload, current_price),
        "availability": availability,
        "seller_name": _first_text(payload, SELLER_SELECTOR),
        "image_url": _first_image(payload, IMAGE_SELECTOR),
    }
    if not _has_product_signal(values):
        raise PageStructureChangedError(
            "Wildberries Apify item does not match expected product payload",
            raw_payload={"item": dict(payload)},
        )
    return values


def is_antibot_payload(payload: Mapping[str, Any]) -> bool:
    return _contains_marker(payload, ANTI_BOT_MARKERS)


def is_not_found_payload(payload: Mapping[str, Any]) -> bool:
    return _contains_marker(payload, NOT_FOUND_MARKERS)


def first_int(payload: Mapping[str, Any], selector: FieldSelector) -> int | None:
    value = _first_by_selector(payload, selector)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def first_text(payload: Mapping[str, Any], selector: FieldSelector) -> str | None:
    return _first_text(payload, selector)


def _has_product_signal(values: Mapping[str, Any]) -> bool:
    return bool(
        values.get("title")
        or values.get("current_price") is not None
        or values.get("availability") != AvailabilityStatus.UNKNOWN
    )


def _first_by_selector(payload: Mapping[str, Any], selector: FieldSelector) -> Any:
    for path in selector.paths:
        value = _value_at_path(payload, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _value_at_path(payload: Mapping[str, Any], path: Path) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _first_text(payload: Mapping[str, Any], selector: FieldSelector) -> str | None:
    value = _first_by_selector(payload, selector)
    if isinstance(value, Mapping):
        value = _first_mapping_value(value, ("name", "title", "value", "text"))
    if value is None:
        return None
    return str(value).strip() or None


def _first_image(payload: Mapping[str, Any], selector: FieldSelector) -> str | None:
    value = _first_by_selector(payload, selector)
    if isinstance(value, Sequence) and not isinstance(value, str):
        value = next((item for item in value if item), None)
    if isinstance(value, Mapping):
        value = _first_mapping_value(value, ("url", "src", "big", "c246x328"))
    if value is None:
        return None
    return str(value).strip() or None


def _first_price(payload: Mapping[str, Any], selector: FieldSelector) -> Decimal | None:
    for path in selector.paths:
        value = _value_at_path(payload, path)
        price = _parse_decimal(value)
        if price is not None:
            if path[-1].endswith("U") or path[-1].endswith("_u"):
                return price / Decimal("100")
            return price
    return None


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return _parse_decimal(_first_mapping_value(value, ("amount", "value", "price")))

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


def _extract_currency(payload: Mapping[str, Any], current_price: Decimal | None) -> str | None:
    value = _first_by_selector(payload, CURRENCY_SELECTOR)
    if value is None and current_price is not None:
        return "RUB"
    if value is None:
        return None

    text = str(value).strip().upper()
    currency_map = {"₽": "RUB", "Р": "RUB", "РУБ": "RUB", "RUR": "RUB"}
    return currency_map.get(text, text)


def _extract_availability(payload: Mapping[str, Any]) -> AvailabilityStatus:
    value = _first_by_selector(payload, AVAILABILITY_SELECTOR)
    if isinstance(value, bool):
        return AvailabilityStatus.IN_STOCK if value else AvailabilityStatus.UNAVAILABLE
    if isinstance(value, int | float):
        return AvailabilityStatus.IN_STOCK if value > 0 else AvailabilityStatus.UNAVAILABLE
    if value is None:
        return AvailabilityStatus.UNKNOWN

    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"true", "available", "in_stock", "instock", "yes", "1"}:
        return AvailabilityStatus.IN_STOCK
    if text in {
        "false",
        "unavailable",
        "out_of_stock",
        "outofstock",
        "sold_out",
        "no",
        "0",
        "нет_в_наличии",
    }:
        return AvailabilityStatus.UNAVAILABLE
    if text in {"preorder", "pre_order"}:
        return AvailabilityStatus.PREORDER
    return AvailabilityStatus.UNKNOWN


def _first_mapping_value(payload: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _contains_marker(payload: Mapping[str, Any], markers: Sequence[str]) -> bool:
    text = str(payload).lower()
    return any(marker in text for marker in markers)


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

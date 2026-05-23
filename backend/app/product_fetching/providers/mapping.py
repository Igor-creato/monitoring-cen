import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import AvailabilityStatus

_CURRENT_PRICE_KEYS = (
    "current_price",
    "currentPrice",
    "price",
    "priceValue",
    "salePrice",
    "finalPrice",
    "discountedPrice",
)
_OLD_PRICE_KEYS = ("old_price", "oldPrice", "originalPrice", "listPrice", "regularPrice")
_TITLE_KEYS = ("title", "name", "productName")
_CURRENCY_KEYS = ("currency", "currencyCode", "currencyRaw")
_SELLER_KEYS = ("seller_name", "sellerName", "seller", "merchantName", "vendor")
_IMAGE_KEYS = ("image_url", "imageUrl", "image", "mainImage", "thumbnail")
_AVAILABILITY_KEYS = ("availability", "availabilityStatus", "inStock", "isAvailable", "stock")


def extract_snapshot_values(payload: Mapping[str, Any]) -> dict[str, Any]:
    current_price = _first_decimal(payload, _CURRENT_PRICE_KEYS)
    return {
        "title": _first_text(payload, _TITLE_KEYS),
        "current_price": current_price,
        "old_price": _first_decimal(payload, _OLD_PRICE_KEYS),
        "currency": _extract_currency(payload, current_price),
        "availability": _extract_availability(payload),
        "seller_name": _first_text(payload, _SELLER_KEYS),
        "image_url": _first_image(payload, _IMAGE_KEYS),
    }


def _first_value(payload: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    value = _first_value(payload, keys)
    if isinstance(value, Mapping):
        value = _first_value(value, ("name", "title", "value", "text"))
    if value is None:
        return None
    return str(value).strip() or None


def _first_image(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    value = _first_value(payload, keys)
    if isinstance(value, Sequence) and not isinstance(value, str):
        value = next((item for item in value if item), None)
    if isinstance(value, Mapping):
        value = _first_value(value, ("url", "src", "imageUrl"))
    if value is None:
        return None
    return str(value).strip() or None


def _first_decimal(payload: Mapping[str, Any], keys: Sequence[str]) -> Decimal | None:
    return _parse_decimal(_first_value(payload, keys))


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return _parse_decimal(_first_value(value, ("amount", "value", "price")))

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


def _extract_currency(payload: Mapping[str, Any], price: Decimal | None) -> str | None:
    value = _first_value(payload, _CURRENCY_KEYS)
    if value is None:
        price_value = _first_value(payload, _CURRENT_PRICE_KEYS)
        if isinstance(price_value, Mapping):
            value = _first_value(price_value, _CURRENCY_KEYS)
    if value is None and price is not None:
        return "RUB"

    text = str(value).strip().upper() if value is not None else None
    currency_map = {"₽": "RUB", "Р": "RUB", "РУБ": "RUB", "RUR": "RUB", "$": "USD", "€": "EUR"}
    return currency_map.get(text, text)


def _extract_availability(payload: Mapping[str, Any]) -> AvailabilityStatus:
    value = _first_value(payload, _AVAILABILITY_KEYS)
    if isinstance(value, bool):
        return AvailabilityStatus.IN_STOCK if value else AvailabilityStatus.OUT_OF_STOCK
    if value is None:
        return AvailabilityStatus.UNKNOWN

    text = str(value).strip().lower()
    if text in {"true", "available", "in_stock", "instock", "in stock", "yes", "1"}:
        return AvailabilityStatus.IN_STOCK
    if text in {"false", "unavailable", "out_of_stock", "outofstock", "out of stock", "no", "0"}:
        return AvailabilityStatus.OUT_OF_STOCK
    if text in {"preorder", "pre-order", "pre order"}:
        return AvailabilityStatus.PREORDER
    return AvailabilityStatus.UNKNOWN

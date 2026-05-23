from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.product_fetching.exceptions import (
    PageStructureChangedError,
    ProductNotFoundError,
    ProviderBlockedError,
    ProviderPayloadError,
    ProviderRateLimitError,
)
from app.product_fetching.providers.wildberries.mapping import (
    ERROR_CODE_SELECTOR,
    ERROR_MESSAGE_SELECTOR,
    ERROR_STATUS_SELECTOR,
    PRODUCT_CONTAINER_PATHS,
    first_int,
    first_text,
    is_antibot_payload,
    is_not_found_payload,
)


class WildberriesParsedItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_item: dict[str, Any]
    product_payload: dict[str, Any]


class WildberriesApifyDatasetParser:
    def parse_first_product(self, payload: Any) -> WildberriesParsedItem:
        item = self._first_dataset_item(payload)
        self._raise_for_item_error(item)

        product_payload = self._extract_product_payload(item)
        if product_payload is None:
            if is_not_found_payload(item):
                raise ProductNotFoundError(
                    "Wildberries product was not found",
                    raw_payload={"item": item},
                )
            if is_antibot_payload(item):
                raise ProviderBlockedError(
                    "Wildberries response looks blocked by anti-bot protection",
                    raw_payload={"item": item},
                )
            raise PageStructureChangedError(
                "Wildberries product payload was not found in Apify dataset item",
                raw_payload={"item": item},
            )

        return WildberriesParsedItem(raw_item=item, product_payload=product_payload)

    def _first_dataset_item(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, Sequence) and not isinstance(payload, str):
            if not payload:
                raise ProductNotFoundError(
                    "Apify returned an empty dataset",
                    raw_payload={"response": []},
                )
            first_item = payload[0]
        elif isinstance(payload, Mapping):
            first_item = payload
        else:
            raise ProviderPayloadError(
                "Apify dataset response must be a JSON object or array",
                raw_payload={"response": payload},
            )

        if not isinstance(first_item, Mapping):
            raise ProviderPayloadError(
                "Apify dataset item must be an object",
                raw_payload={"item": first_item},
            )
        return dict(first_item)

    def _raise_for_item_error(self, item: Mapping[str, Any]) -> None:
        status_code = first_int(item, ERROR_STATUS_SELECTOR)
        error_code = first_text(item, ERROR_CODE_SELECTOR)
        error_message = first_text(item, ERROR_MESSAGE_SELECTOR)
        raw_payload = {"item": dict(item)}

        if status_code == 404 or is_not_found_payload(item):
            raise ProductNotFoundError(
                error_message or "Wildberries product was not found",
                raw_payload=raw_payload,
            )
        if status_code == 429 or (error_code and "429" in error_code):
            raise ProviderRateLimitError(
                error_message or "Wildberries or Apify reported rate limiting",
                raw_payload=raw_payload,
            )
        if status_code == 403 or is_antibot_payload(item):
            raise ProviderBlockedError(
                error_message or "Wildberries response looks blocked by anti-bot protection",
                raw_payload=raw_payload,
            )

    def _extract_product_payload(self, item: Mapping[str, Any]) -> dict[str, Any] | None:
        for path in PRODUCT_CONTAINER_PATHS:
            value = self._value_at_path(item, path)
            if isinstance(value, list) and value:
                value = value[0]
            if isinstance(value, Mapping) and value:
                return dict(value)

        if self._looks_like_product_payload(item):
            return dict(item)
        return None

    @staticmethod
    def _value_at_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                return None
            current = current[key]
        return current

    @staticmethod
    def _looks_like_product_payload(item: Mapping[str, Any]) -> bool:
        product_keys = {
            "name",
            "title",
            "productName",
            "salePriceU",
            "priceU",
            "inStock",
            "availability",
            "sellerName",
            "supplierName",
        }
        return bool(product_keys.intersection(item.keys()))

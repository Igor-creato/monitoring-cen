from dataclasses import dataclass
from typing import Any

import httpx

from app.domain.enums import Marketplace
from app.product_fetching.base import AbstractProductProvider
from app.product_fetching.exceptions import (
    ProductNotFoundError,
    ProviderBlockedError,
    ProviderConfigurationError,
    ProviderPayloadError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
)
from app.product_fetching.models import ProductSnapshot
from app.product_fetching.providers.mapping import extract_snapshot_values
from app.product_fetching.retry import RetryPolicy


@dataclass(frozen=True, slots=True)
class ZyteProviderConfig:
    api_key: str
    api_url: str = "https://api.zyte.com/v1/extract"
    request_timeout_seconds: float = 60


class ZyteProvider(AbstractProductProvider):
    name = "zyte"

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        config: ZyteProviderConfig,
        retry_policy: RetryPolicy | None = None,
    ):
        super().__init__(retry_policy=retry_policy)
        if not config.api_key:
            raise ProviderConfigurationError("Zyte API key is required", provider_name=self.name)

        self.http_client = http_client
        self.config = config

    async def _fetch_normalized(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
    ) -> ProductSnapshot:
        request_payload: dict[str, Any] = {
            "url": normalized_url,
            "product": True,
        }

        try:
            response = await self.http_client.post(
                self.config.api_url,
                json=request_payload,
                auth=(self.config.api_key, ""),
                timeout=self.config.request_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Zyte request timed out", provider_name=self.name) from exc
        except httpx.TransportError as exc:
            raise ProviderRequestError("Zyte transport error", provider_name=self.name) from exc

        self._raise_for_status(response)
        payload = self._decode_response(response)
        product_payload = self._extract_product_payload(payload)

        return self._success_snapshot(
            normalized_url=normalized_url,
            marketplace=marketplace,
            raw_payload={"request": request_payload, "response": payload},
            **extract_snapshot_values(product_payload),
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise ProviderRateLimitError("Zyte rate limit exceeded", provider_name=self.name)
        if response.status_code in {401, 403}:
            raise ProviderBlockedError(
                f"Zyte authentication or access error: HTTP {response.status_code}",
                provider_name=self.name,
            )
        if response.status_code >= 500:
            raise ProviderRequestError(
                f"Zyte server error: HTTP {response.status_code}",
                provider_name=self.name,
            )
        if response.status_code >= 400:
            raise ProviderRequestError(
                f"Zyte request failed: HTTP {response.status_code}",
                retryable=False,
                provider_name=self.name,
            )

    def _decode_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderPayloadError(
                "Zyte returned non-JSON response",
                provider_name=self.name,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderPayloadError("Zyte response must be an object", provider_name=self.name)
        return payload

    def _extract_product_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        product = payload.get("product") or payload.get("productData") or payload
        if product is None:
            raise ProductNotFoundError("Zyte returned no product data", provider_name=self.name)
        if not isinstance(product, dict):
            raise ProviderPayloadError(
                "Zyte product data must be an object",
                provider_name=self.name,
            )
        return product

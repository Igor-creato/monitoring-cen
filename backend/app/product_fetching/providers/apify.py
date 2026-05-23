from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

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
class ApifyProviderConfig:
    api_token: str
    actor_id: str
    base_url: str = "https://api.apify.com"
    request_timeout_seconds: float = 60


class ApifyProvider(AbstractProductProvider):
    name = "apify"

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        config: ApifyProviderConfig,
        retry_policy: RetryPolicy | None = None,
        input_builder: Callable[[str], Mapping[str, Any]] | None = None,
    ):
        super().__init__(retry_policy=retry_policy)
        if not config.api_token:
            raise ProviderConfigurationError("Apify API token is required", provider_name=self.name)
        if not config.actor_id:
            raise ProviderConfigurationError("Apify actor_id is required", provider_name=self.name)

        self.http_client = http_client
        self.config = config
        self.input_builder = input_builder or self._default_input_builder

    async def _fetch_normalized(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
    ) -> ProductSnapshot:
        actor_id = quote(self.config.actor_id, safe="")
        endpoint = (
            f"{self.config.base_url.rstrip('/')}/v2/acts/"
            f"{actor_id}/run-sync-get-dataset-items"
        )
        request_payload = dict(self.input_builder(normalized_url))

        try:
            response = await self.http_client.post(
                endpoint,
                params={"token": self.config.api_token},
                json=request_payload,
                timeout=self.config.request_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Apify request timed out", provider_name=self.name) from exc
        except httpx.TransportError as exc:
            raise ProviderRequestError(
                "Apify transport error",
                provider_name=self.name,
            ) from exc

        self._raise_for_status(response)
        payload = self._decode_response(response)
        item = self._first_dataset_item(payload)

        return self._success_snapshot(
            normalized_url=normalized_url,
            marketplace=marketplace,
            raw_payload={"request": request_payload, "response": payload},
            **extract_snapshot_values(item),
        )

    @staticmethod
    def _default_input_builder(normalized_url: str) -> Mapping[str, Any]:
        return {
            "url": normalized_url,
            "startUrls": [{"url": normalized_url}],
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise ProviderRateLimitError("Apify rate limit exceeded", provider_name=self.name)
        if response.status_code in {401, 403}:
            raise ProviderBlockedError(
                f"Apify authentication or access error: HTTP {response.status_code}",
                provider_name=self.name,
            )
        if response.status_code >= 500:
            raise ProviderRequestError(
                f"Apify server error: HTTP {response.status_code}",
                provider_name=self.name,
            )
        if response.status_code >= 400:
            raise ProviderRequestError(
                f"Apify request failed: HTTP {response.status_code}",
                retryable=False,
                provider_name=self.name,
            )

    def _decode_response(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderPayloadError(
                "Apify returned non-JSON response",
                provider_name=self.name,
            ) from exc

    def _first_dataset_item(self, payload: Any) -> Mapping[str, Any]:
        if isinstance(payload, list) and payload:
            first_item = payload[0]
        elif isinstance(payload, dict):
            first_item = payload
        else:
            raise ProductNotFoundError("Apify returned an empty dataset", provider_name=self.name)

        if not isinstance(first_item, Mapping):
            raise ProviderPayloadError(
                "Apify dataset item must be an object",
                provider_name=self.name,
            )
        return first_item

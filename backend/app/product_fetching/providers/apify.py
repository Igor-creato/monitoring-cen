from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from app.domain.enums import Marketplace
from app.product_fetching.base import AbstractProductProvider
from app.product_fetching.exceptions import (
    ProviderBlockedError,
    ProviderConfigurationError,
    ProviderPayloadError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    UnsupportedProductUrlError,
)
from app.product_fetching.models import ProductSnapshot
from app.product_fetching.providers.wildberries import (
    WildberriesApifyDatasetParser,
    build_apify_input,
    map_product_payload,
)
from app.product_fetching.retry import RetryPolicy


@dataclass(frozen=True, slots=True)
class ApifyProviderConfig:
    api_token: str
    actor_id: str
    base_url: str = "https://api.apify.com"
    request_timeout_seconds: float = 60


@dataclass(frozen=True, slots=True)
class ApifyActorRunResult:
    request_payload: dict[str, Any]
    response_payload: Any


class ApifyActorClient:
    def __init__(self, *, http_client: httpx.AsyncClient, config: ApifyProviderConfig):
        if not config.api_token:
            raise ProviderConfigurationError("Apify API token is required", provider_name="apify")
        if not config.actor_id:
            raise ProviderConfigurationError("Apify actor_id is required", provider_name="apify")

        self.http_client = http_client
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)

    async def run_sync_get_dataset_items(
        self,
        *,
        input_payload: Mapping[str, Any],
    ) -> ApifyActorRunResult:
        request_payload = dict(input_payload)
        endpoint = self._endpoint()

        try:
            response = await self.http_client.post(
                endpoint,
                params={"timeout": int(self.config.request_timeout_seconds), "clean": "true"},
                headers={"Authorization": f"Bearer {self.config.api_token}"},
                json=request_payload,
                timeout=self.config.request_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Apify request timed out", provider_name="apify") from exc
        except httpx.TransportError as exc:
            raise ProviderRequestError("Apify transport error", provider_name="apify") from exc

        payload = self._decode_response(response)
        self._raise_for_status(response, payload)
        return ApifyActorRunResult(request_payload=request_payload, response_payload=payload)

    def _endpoint(self) -> str:
        actor_id = quote(self.config.actor_id, safe="")
        return (
            f"{self.config.base_url.rstrip('/')}/v2/acts/"
            f"{actor_id}/run-sync-get-dataset-items"
        )

    def _decode_response(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderPayloadError(
                "Apify returned non-JSON response",
                provider_name="apify",
                raw_payload={"status_code": response.status_code, "text": response.text[:1000]},
            ) from exc

    def _raise_for_status(self, response: httpx.Response, payload: Any) -> None:
        if response.status_code < 400:
            return

        raw_payload = {"status_code": response.status_code, "response": payload}
        message = (
            self._error_message(payload)
            or f"Apify request failed: HTTP {response.status_code}"
        )
        error_type = self._error_type(payload)

        self.logger.warning(
            "Apify API request failed",
            status_code=response.status_code,
            error_type=error_type,
        )

        if response.status_code in {408, 504} or self._looks_like_timeout(error_type, message):
            raise ProviderTimeoutError(message, provider_name="apify", raw_payload=raw_payload)
        if response.status_code == 429 or self._looks_like_rate_limit(error_type, message):
            raise ProviderRateLimitError(message, provider_name="apify", raw_payload=raw_payload)
        if response.status_code in {401, 403}:
            raise ProviderBlockedError(message, provider_name="apify", raw_payload=raw_payload)
        if response.status_code >= 500:
            raise ProviderRequestError(message, provider_name="apify", raw_payload=raw_payload)
        raise ProviderRequestError(
            message,
            retryable=False,
            provider_name="apify",
            raw_payload=raw_payload,
        )

    @staticmethod
    def _error_message(payload: Any) -> str | None:
        if not isinstance(payload, Mapping):
            return None
        error = payload.get("error")
        if isinstance(error, Mapping):
            value = error.get("message")
            return str(value) if value else None
        value = payload.get("message")
        return str(value) if value else None

    @staticmethod
    def _error_type(payload: Any) -> str | None:
        if not isinstance(payload, Mapping):
            return None
        error = payload.get("error")
        if isinstance(error, Mapping):
            value = error.get("type") or error.get("code")
            return str(value) if value else None
        value = payload.get("type") or payload.get("code")
        return str(value) if value else None

    @staticmethod
    def _looks_like_timeout(error_type: str | None, message: str) -> bool:
        text = f"{error_type or ''} {message}".lower()
        return "timeout" in text or "timed out" in text

    @staticmethod
    def _looks_like_rate_limit(error_type: str | None, message: str) -> bool:
        text = f"{error_type or ''} {message}".lower()
        return "rate limit" in text or "too many requests" in text


class ApifyProvider(AbstractProductProvider):
    name = "apify"
    marketplace = Marketplace.WILDBERRIES

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        config: ApifyProviderConfig,
        retry_policy: RetryPolicy | None = None,
        input_builder: Callable[[str], Mapping[str, Any]] | None = None,
        actor_client: ApifyActorClient | None = None,
        dataset_parser: WildberriesApifyDatasetParser | None = None,
    ):
        super().__init__(retry_policy=retry_policy)
        self.actor_client = actor_client or ApifyActorClient(
            http_client=http_client,
            config=config,
        )
        self.input_builder = input_builder or build_apify_input
        self.dataset_parser = dataset_parser or WildberriesApifyDatasetParser()

    async def _fetch_normalized(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
    ) -> ProductSnapshot:
        if marketplace != self.marketplace:
            raise UnsupportedProductUrlError(
                "Apify production adapter currently supports only Wildberries product URLs",
                provider_name=self.name,
            )

        actor_result = await self.actor_client.run_sync_get_dataset_items(
            input_payload=self.input_builder(normalized_url),
        )
        parsed_item = self.dataset_parser.parse_first_product(actor_result.response_payload)
        snapshot_values = map_product_payload(parsed_item.product_payload)

        return self._success_snapshot(
            normalized_url=normalized_url,
            marketplace=marketplace,
            raw_payload={
                "provider": self.name,
                "marketplace": self.marketplace,
                "request": actor_result.request_payload,
                "response": actor_result.response_payload,
                "item": parsed_item.raw_item,
            },
            **snapshot_values,
        )

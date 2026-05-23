from dataclasses import dataclass
from enum import StrEnum

import httpx

from app.infra.config import Settings, get_settings
from app.product_fetching.base import ProductDataProvider
from app.product_fetching.exceptions import ProviderConfigurationError
from app.product_fetching.providers import (
    ApifyProvider,
    ApifyProviderConfig,
    MockProvider,
    ZyteProvider,
    ZyteProviderConfig,
)
from app.product_fetching.retry import ExponentialBackoffRetryPolicy, RetryPolicy


class ProductProviderKind(StrEnum):
    APIFY = "apify"
    ZYTE = "zyte"
    MOCK = "mock"


@dataclass(slots=True)
class ProductProviderFactory:
    http_client: httpx.AsyncClient
    settings: Settings
    retry_policy: RetryPolicy | None = None

    def create(self, provider: ProductProviderKind | str | None = None) -> ProductDataProvider:
        provider_kind = self._parse_provider(provider or self.settings.product_fetch_provider)
        retry_policy = self.retry_policy or self._build_retry_policy()

        if provider_kind == ProductProviderKind.APIFY:
            return ApifyProvider(
                http_client=self.http_client,
                config=ApifyProviderConfig(
                    api_token=self._required_setting("apify_api_token"),
                    actor_id=self._required_setting("apify_actor_id"),
                    base_url=self.settings.apify_base_url,
                    request_timeout_seconds=self.settings.product_fetch_request_timeout_seconds,
                ),
                retry_policy=retry_policy,
            )

        if provider_kind == ProductProviderKind.ZYTE:
            return ZyteProvider(
                http_client=self.http_client,
                config=ZyteProviderConfig(
                    api_key=self._required_setting("zyte_api_key"),
                    api_url=self.settings.zyte_api_url,
                    request_timeout_seconds=self.settings.product_fetch_request_timeout_seconds,
                ),
                retry_policy=retry_policy,
            )

        return MockProvider(retry_policy=retry_policy)

    def _build_retry_policy(self) -> ExponentialBackoffRetryPolicy:
        return ExponentialBackoffRetryPolicy(
            max_attempts=self.settings.product_fetch_retry_max_attempts,
            base_delay_seconds=self.settings.product_fetch_retry_base_delay_seconds,
            max_delay_seconds=self.settings.product_fetch_retry_max_delay_seconds,
            jitter_ratio=self.settings.product_fetch_retry_jitter_ratio,
        )

    def _required_setting(self, field_name: str) -> str:
        value = getattr(self.settings, field_name)
        if not value:
            raise ProviderConfigurationError(f"{field_name.upper()} is required")
        return value

    @staticmethod
    def _parse_provider(provider: ProductProviderKind | str) -> ProductProviderKind:
        try:
            return ProductProviderKind(provider)
        except ValueError as exc:
            supported = ", ".join(kind.value for kind in ProductProviderKind)
            raise ProviderConfigurationError(
                f"Unsupported product fetch provider '{provider}'. "
                f"Supported providers: {supported}",
            ) from exc


def create_product_provider(
    http_client: httpx.AsyncClient,
    *,
    settings: Settings | None = None,
    provider: ProductProviderKind | str | None = None,
    retry_policy: RetryPolicy | None = None,
) -> ProductDataProvider:
    return ProductProviderFactory(
        http_client=http_client,
        settings=settings or get_settings(),
        retry_policy=retry_policy,
    ).create(provider)

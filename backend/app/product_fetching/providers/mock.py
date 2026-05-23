from collections.abc import Mapping
from typing import Any

from app.domain.enums import Marketplace
from app.product_fetching.base import AbstractProductProvider
from app.product_fetching.exceptions import ProductNotFoundError
from app.product_fetching.models import ProductSnapshot
from app.product_fetching.providers.mapping import extract_snapshot_values
from app.product_fetching.retry import RetryPolicy


class MockProvider(AbstractProductProvider):
    name = "mock"

    def __init__(
        self,
        *,
        fixtures: Mapping[str, ProductSnapshot | Mapping[str, Any]] | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        super().__init__(retry_policy=retry_policy)
        self.fixtures = dict(fixtures or {})

    async def _fetch_normalized(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
    ) -> ProductSnapshot:
        fixture = self.fixtures.get(normalized_url)
        if fixture is None:
            raise ProductNotFoundError(
                f"Mock fixture is not registered for URL: {normalized_url}",
                provider_name=self.name,
            )

        if isinstance(fixture, ProductSnapshot):
            return fixture.model_copy(
                update={
                    "normalized_url": normalized_url,
                    "marketplace": marketplace,
                },
            )

        raw_payload = dict(fixture)
        return self._success_snapshot(
            normalized_url=normalized_url,
            marketplace=marketplace,
            raw_payload=raw_payload,
            **extract_snapshot_values(raw_payload),
        )

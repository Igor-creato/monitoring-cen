from abc import ABC, abstractmethod
from typing import Protocol

import structlog

from app.domain.enums import Marketplace
from app.domain.url_normalization import normalize_product_url
from app.product_fetching.exceptions import ProductFetchError
from app.product_fetching.models import ProductSnapshot
from app.product_fetching.retry import NoRetryPolicy, RetryPolicy


class ProductDataProvider(Protocol):
    name: str

    async def fetch_product(self, url: str) -> ProductSnapshot: ...


class AbstractProductProvider(ABC):
    name: str

    def __init__(self, *, retry_policy: RetryPolicy | None = None):
        self.retry_policy = retry_policy or NoRetryPolicy()
        self.logger = structlog.get_logger(self.__class__.__name__)

    async def fetch_product(self, url: str) -> ProductSnapshot:
        normalized = normalize_product_url(url)
        snapshot_url = normalized.normalized_url or normalized.original_url or url

        if not normalized.is_supported or normalized.normalized_url is None:
            return self._failure_snapshot(
                normalized_url=snapshot_url,
                marketplace=normalized.marketplace,
                error_code="unsupported_product_url",
                error_message=normalized.reason_if_invalid or "Unsupported product URL",
            )

        try:
            return await self.retry_policy.run(
                lambda: self._fetch_normalized(
                    normalized_url=normalized.normalized_url,
                    marketplace=normalized.marketplace,
                ),
                operation_name=f"{self.name}.fetch_product",
            )
        except ProductFetchError as exc:
            return self._failure_snapshot(
                normalized_url=normalized.normalized_url,
                marketplace=normalized.marketplace,
                error_code=exc.error_code,
                error_message=exc.error_message,
            )
        except Exception as exc:
            self.logger.exception(
                "Unexpected product fetch error",
                provider=self.name,
                marketplace=normalized.marketplace,
                normalized_url=normalized.normalized_url,
            )
            return self._failure_snapshot(
                normalized_url=normalized.normalized_url,
                marketplace=normalized.marketplace,
                error_code="unexpected_product_fetch_error",
                error_message=str(exc) or exc.__class__.__name__,
            )

    @abstractmethod
    async def _fetch_normalized(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
    ) -> ProductSnapshot: ...

    def _success_snapshot(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
        **values: object,
    ) -> ProductSnapshot:
        return ProductSnapshot(
            normalized_url=normalized_url,
            marketplace=marketplace,
            success=True,
            **values,
        )

    def _failure_snapshot(
        self,
        *,
        normalized_url: str,
        marketplace: Marketplace,
        error_code: str,
        error_message: str,
        raw_payload: dict[str, object] | None = None,
    ) -> ProductSnapshot:
        return ProductSnapshot(
            normalized_url=normalized_url,
            marketplace=marketplace,
            raw_payload=raw_payload or {},
            success=False,
            error_code=error_code,
            error_message=error_message,
        )

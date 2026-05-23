import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from app.product_fetching.exceptions import ProductFetchError

T = TypeVar("T")


class RetryPolicy(Protocol):
    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        operation_name: str,
        is_retryable: Callable[[BaseException], bool] | None = None,
    ) -> T: ...


class NoRetryPolicy:
    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        operation_name: str,
        is_retryable: Callable[[BaseException], bool] | None = None,
    ) -> T:
        return await operation()


class ExponentialBackoffRetryPolicy:
    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_delay_seconds: float = 0.25,
        max_delay_seconds: float = 5.0,
        jitter_ratio: float = 0.2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be greater than or equal to 1")
        if base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be greater than or equal to 0")
        if max_delay_seconds < base_delay_seconds:
            raise ValueError(
                "max_delay_seconds must be greater than or equal to base_delay_seconds",
            )
        if jitter_ratio < 0:
            raise ValueError("jitter_ratio must be greater than or equal to 0")

        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.jitter_ratio = jitter_ratio
        self._sleep = sleep

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        operation_name: str,
        is_retryable: Callable[[BaseException], bool] | None = None,
    ) -> T:
        should_retry = is_retryable or _default_is_retryable

        for attempt in range(1, self.max_attempts + 1):
            try:
                return await operation()
            except BaseException as exc:
                if attempt == self.max_attempts or not should_retry(exc):
                    raise
                await self._sleep(self._delay_for_attempt(attempt))

        raise RuntimeError(f"retry loop exited unexpectedly for {operation_name}")

    def _delay_for_attempt(self, attempt: int) -> float:
        delay = min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)
        if delay == 0 or self.jitter_ratio == 0:
            return delay

        jitter = delay * self.jitter_ratio
        return max(0.0, delay + random.uniform(-jitter, jitter))


def _default_is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, ProductFetchError) and exc.retryable

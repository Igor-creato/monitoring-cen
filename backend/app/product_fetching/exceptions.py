class ProductFetchError(Exception):
    """Base class for provider-neutral product fetching errors."""

    error_code = "product_fetch_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        retryable: bool | None = None,
        provider_name: str | None = None,
    ):
        super().__init__(message)
        self.error_message = message
        self.error_code = error_code or self.error_code
        self.retryable = self.retryable if retryable is None else retryable
        self.provider_name = provider_name


class UnsupportedProductUrlError(ProductFetchError):
    error_code = "unsupported_product_url"


class ProviderConfigurationError(ProductFetchError):
    error_code = "provider_configuration_error"


class ProviderRequestError(ProductFetchError):
    error_code = "provider_request_error"
    retryable = True


class ProviderTimeoutError(ProviderRequestError):
    error_code = "provider_timeout"


class ProviderRateLimitError(ProviderRequestError):
    error_code = "provider_rate_limited"


class ProviderBlockedError(ProviderRequestError):
    error_code = "provider_blocked"
    retryable = False


class ProviderPayloadError(ProductFetchError):
    error_code = "provider_payload_error"


class ProductNotFoundError(ProductFetchError):
    error_code = "product_not_found"

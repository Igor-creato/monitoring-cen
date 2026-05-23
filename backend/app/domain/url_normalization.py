from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse, urlunparse

from app.domain.enums import Marketplace


@dataclass(frozen=True, slots=True)
class ProductUrlNormalizationResult:
    original_url: str
    normalized_url: str | None
    marketplace: Marketplace
    is_supported: bool
    reason_if_invalid: str | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceUrlRule:
    marketplace: Marketplace
    canonical_host: str
    allowed_hosts: frozenset[str]
    normalize_path: Callable[[tuple[str, ...]], str | None]

    def matches_host(self, host: str) -> bool:
        return host in self.allowed_hosts


def normalize_product_url(url: str) -> ProductUrlNormalizationResult:
    original_url = url.strip()
    if not original_url:
        return _invalid(url, Marketplace.UNKNOWN, "URL is empty")

    try:
        parsed = urlparse(original_url)
        host = _normalized_host(parsed.hostname)
        _ = parsed.port
    except ValueError:
        return _invalid(original_url, Marketplace.UNKNOWN, "URL host or port is invalid")

    if parsed.scheme.lower() not in {"http", "https"}:
        return _invalid(original_url, Marketplace.UNKNOWN, "URL scheme must be http or https")
    if host is None:
        return _invalid(original_url, Marketplace.UNKNOWN, "URL host is missing")
    if parsed.username or parsed.password:
        return _invalid(original_url, Marketplace.UNKNOWN, "URL must not contain credentials")

    rule = _rule_for_host(host)
    if rule is None:
        return _invalid(original_url, Marketplace.UNKNOWN, "Marketplace domain is not supported")

    path_segments = _path_segments(parsed.path)
    normalized_path = rule.normalize_path(path_segments)
    if normalized_path is None:
        return _invalid(
            original_url,
            rule.marketplace,
            "URL is not a supported product card",
        )

    normalized_url = urlunparse(("https", rule.canonical_host, normalized_path, "", "", ""))
    return ProductUrlNormalizationResult(
        original_url=original_url,
        normalized_url=normalized_url,
        marketplace=rule.marketplace,
        is_supported=True,
    )


def _invalid(
    original_url: str,
    marketplace: Marketplace,
    reason: str,
) -> ProductUrlNormalizationResult:
    return ProductUrlNormalizationResult(
        original_url=original_url,
        normalized_url=None,
        marketplace=marketplace,
        is_supported=False,
        reason_if_invalid=reason,
    )


def _rule_for_host(host: str) -> MarketplaceUrlRule | None:
    return next((rule for rule in _RULES if rule.matches_host(host)), None)


def _normalized_host(host: str | None) -> str | None:
    if host is None:
        return None
    normalized = host.strip().lower().rstrip(".")
    return normalized or None


def _path_segments(path: str) -> tuple[str, ...]:
    return tuple(segment for segment in path.split("/") if segment)


def _normalize_ozon_path(segments: tuple[str, ...]) -> str | None:
    if len(segments) < 2 or segments[0].lower() != "product":
        return None

    product_segment = unquote(segments[1])
    product_id = _trailing_numeric_token(product_segment)
    if product_id is None:
        return None

    return f"/product/{_safe_path_segment(product_segment)}/"


def _normalize_wildberries_path(segments: tuple[str, ...]) -> str | None:
    if len(segments) < 3:
        return None
    if segments[0].lower() != "catalog":
        return None

    product_id = segments[1]
    detail_page = segments[2].lower()
    if not product_id.isdigit() or detail_page != "detail.aspx":
        return None

    return f"/catalog/{product_id}/detail.aspx"


def _normalize_yandex_market_path(segments: tuple[str, ...]) -> str | None:
    if len(segments) < 2:
        return None

    slug_segment = unquote(segments[0])
    product_id = segments[1]
    if not slug_segment.lower().startswith("product--") or not product_id.isdigit():
        return None

    return f"/{_safe_path_segment(slug_segment)}/{product_id}"


def _trailing_numeric_token(segment: str) -> str | None:
    token = segment.rsplit("-", maxsplit=1)[-1]
    if not token.isdigit():
        return None
    return token


def _safe_path_segment(segment: str) -> str:
    return quote(segment, safe="-._~")


_RULES = (
    MarketplaceUrlRule(
        marketplace=Marketplace.OZON,
        canonical_host="www.ozon.ru",
        allowed_hosts=frozenset({"ozon.ru", "www.ozon.ru", "m.ozon.ru"}),
        normalize_path=_normalize_ozon_path,
    ),
    MarketplaceUrlRule(
        marketplace=Marketplace.WILDBERRIES,
        canonical_host="www.wildberries.ru",
        allowed_hosts=frozenset({"wildberries.ru", "www.wildberries.ru", "m.wildberries.ru"}),
        normalize_path=_normalize_wildberries_path,
    ),
    MarketplaceUrlRule(
        marketplace=Marketplace.YANDEX_MARKET,
        canonical_host="market.yandex.ru",
        allowed_hosts=frozenset({"market.yandex.ru", "www.market.yandex.ru", "m.market.yandex.ru"}),
        normalize_path=_normalize_yandex_market_path,
    ),
)

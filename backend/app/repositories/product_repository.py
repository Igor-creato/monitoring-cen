import hashlib
from collections.abc import Mapping
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clock import utc_now
from app.domain.enums import SourceStatus
from app.domain.exceptions import EntityNotFoundError
from app.infra.db.models.monitor import MonitorModel
from app.infra.db.models.parser_error import ParserErrorModel
from app.infra.db.models.product import ProductModel
from app.infra.db.models.product_source import ProductSourceModel
from app.product_fetching.models import ProductSnapshot


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_raise(self, product_id: int) -> ProductModel:
        result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise EntityNotFoundError(f"Product {product_id} was not found")
        return product

    async def get_for_user_or_raise(self, product_id: int, user_id: int) -> ProductModel:
        result = await self.session.execute(
            select(ProductModel)
            .join(ProductSourceModel)
            .join(MonitorModel)
            .where(ProductModel.id == product_id)
            .where(MonitorModel.user_id == user_id)
            .where(MonitorModel.deleted_at.is_(None))
            .limit(1)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise EntityNotFoundError(f"Product {product_id} was not found")
        return product

    async def get_source_by_normalized_url(self, normalized_url: str) -> ProductSourceModel | None:
        domain = _domain_from_url(normalized_url)
        url_hash = _url_hash(normalized_url)
        result = await self.session.execute(
            select(ProductSourceModel)
            .where(ProductSourceModel.domain == domain)
            .where(ProductSourceModel.normalized_url_hash == url_hash)
        )
        return result.scalar_one_or_none()

    async def get_or_create_source(
        self,
        *,
        original_url: str,
        normalized_url: str,
        snapshot: ProductSnapshot,
    ) -> ProductSourceModel:
        source = await self.get_source_by_normalized_url(normalized_url)
        if source is not None:
            return source

        product = ProductModel(
            marketplace=snapshot.marketplace,
            title=snapshot.title,
        )
        source = ProductSourceModel(
            product=product,
            original_url=original_url,
            normalized_url=normalized_url,
            normalized_url_hash=_url_hash(normalized_url),
            domain=_domain_from_url(normalized_url),
            marketplace=snapshot.marketplace,
            title=snapshot.title,
        )
        self.session.add(source)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_source_by_normalized_url(normalized_url)
            if existing is None:
                raise
            return existing
        return source

    async def apply_success_snapshot(
        self,
        source: ProductSourceModel,
        snapshot: ProductSnapshot,
    ) -> None:
        now = utc_now()
        source.marketplace = snapshot.marketplace
        source.title = snapshot.title or source.title
        source.current_price = snapshot.current_price
        source.old_price = snapshot.old_price
        source.currency = snapshot.currency
        source.availability = snapshot.availability
        source.seller_name = snapshot.seller_name
        source.status = SourceStatus.ACTIVE
        source.last_checked_at = now
        source.last_success_at = now
        source.last_error_code = None
        source.last_error_message = None
        if source.product_id is not None:
            product = await self.session.get(ProductModel, source.product_id)
            if product is not None:
                product.marketplace = snapshot.marketplace
                product.title = snapshot.title or product.title

    async def apply_failure_snapshot(
        self,
        source: ProductSourceModel | None,
        snapshot: ProductSnapshot,
    ) -> None:
        if source is None:
            return
        now = utc_now()
        source.status = SourceStatus.ERROR
        source.last_checked_at = now
        source.last_error_at = now
        source.last_error_code = snapshot.error_code
        source.last_error_message = snapshot.error_message

    async def record_parser_error(
        self,
        *,
        source: ProductSourceModel,
        monitor_id: int | None,
        snapshot: ProductSnapshot,
        retryable: bool,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ParserErrorModel:
        raw_payload = snapshot.raw_payload if isinstance(snapshot.raw_payload, Mapping) else {}
        parser_error = ParserErrorModel(
            product_source_id=source.id,
            monitor_id=monitor_id,
            occurred_at=snapshot.fetched_at,
            error_code=error_code or snapshot.error_code or "unknown_parser_error",
            error_message=error_message or snapshot.error_message,
            parser_version=_raw_string(raw_payload, "parser_version"),
            http_status=_raw_int(raw_payload, "status_code"),
            response_time_ms=_raw_int(raw_payload, "response_time_ms"),
            retryable=retryable,
        )
        self.session.add(parser_error)
        await self.session.flush()
        return parser_error


def _url_hash(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def _domain_from_url(normalized_url: str) -> str:
    parsed = urlparse(normalized_url)
    return (parsed.hostname or "").lower()


def _raw_string(raw_payload: Mapping, key: str) -> str | None:
    value = raw_payload.get(key)
    return str(value) if value is not None else None


def _raw_int(raw_payload: Mapping, key: str) -> int | None:
    value = raw_payload.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None

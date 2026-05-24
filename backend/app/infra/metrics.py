from datetime import timedelta

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clock import utc_now
from app.domain.enums import CheckStatus, MonitorStatus, NotificationStatus
from app.infra.db.models.monitor import MonitorModel
from app.infra.db.models.notification import NotificationModel
from app.infra.db.models.parser_error import ParserErrorModel
from app.infra.db.models.price_check import PriceCheckModel

RATE_WINDOW_SECONDS = 900

MONITORS_TOTAL = Gauge("monitors_total", "Total non-deleted price monitors.")
ACTIVE_MONITORS = Gauge("active_monitors", "Active non-deleted price monitors.")

CHECKS_TOTAL = Counter(
    "price_checks_total",
    "Price check attempts grouped by outcome.",
    ("status", "marketplace", "error_code"),
)
CHECK_SUCCESS_RATE = Gauge(
    "check_success_rate",
    "Successful price checks divided by all checks in the rolling window.",
)
CHECK_DURATION = Histogram(
    "check_duration",
    "Price check duration in seconds.",
    ("marketplace",),
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)

NOTIFICATION_SENDS_TOTAL = Counter(
    "notification_sends_total",
    "Notification delivery attempts grouped by outcome.",
    ("status", "channel", "error_code"),
)
NOTIFICATION_SEND_RATE = Gauge(
    "notification_send_rate",
    "Successfully sent notifications per second in the rolling window.",
)

PARSER_ERRORS_TOTAL = Counter(
    "parser_errors_total",
    "Parser/external-site errors grouped by marketplace and code.",
    ("marketplace", "error_code", "retryable"),
)
PARSER_ERROR_RATE = Gauge(
    "parser_error_rate",
    "Parser/external-site errors per second in the rolling window.",
)


def observe_check(
    *,
    status: str,
    marketplace: str,
    error_code: str | None,
    duration_seconds: float,
) -> None:
    CHECKS_TOTAL.labels(
        status=status,
        marketplace=marketplace,
        error_code=error_code or "none",
    ).inc()
    CHECK_DURATION.labels(marketplace=marketplace).observe(duration_seconds)


def observe_notification_send(
    *,
    status: str,
    channel: str,
    error_code: str | None = None,
) -> None:
    NOTIFICATION_SENDS_TOTAL.labels(
        status=status,
        channel=channel,
        error_code=error_code or "none",
    ).inc()


def observe_parser_error(
    *,
    marketplace: str,
    error_code: str,
    retryable: bool,
) -> None:
    PARSER_ERRORS_TOTAL.labels(
        marketplace=marketplace,
        error_code=error_code,
        retryable=str(retryable).lower(),
    ).inc()


async def refresh_database_metrics(session: AsyncSession) -> None:
    window_start = utc_now() - timedelta(seconds=RATE_WINDOW_SECONDS)

    total_monitors = await session.scalar(
        select(func.count()).select_from(MonitorModel).where(MonitorModel.deleted_at.is_(None))
    )
    active_monitors = await session.scalar(
        select(func.count())
        .select_from(MonitorModel)
        .where(MonitorModel.deleted_at.is_(None))
        .where(MonitorModel.status == MonitorStatus.ACTIVE)
    )
    MONITORS_TOTAL.set(total_monitors or 0)
    ACTIVE_MONITORS.set(active_monitors or 0)

    total_checks = await session.scalar(
        select(func.count())
        .select_from(PriceCheckModel)
        .where(PriceCheckModel.checked_at >= window_start)
    )
    success_checks = await session.scalar(
        select(func.count())
        .select_from(PriceCheckModel)
        .where(PriceCheckModel.checked_at >= window_start)
        .where(PriceCheckModel.status == CheckStatus.SUCCESS)
    )
    CHECK_SUCCESS_RATE.set((success_checks or 0) / total_checks if total_checks else 1.0)

    sent_notifications = await session.scalar(
        select(func.count())
        .select_from(NotificationModel)
        .where(NotificationModel.sent_at >= window_start)
        .where(NotificationModel.status == NotificationStatus.SENT)
    )
    NOTIFICATION_SEND_RATE.set((sent_notifications or 0) / RATE_WINDOW_SECONDS)

    parser_errors = await session.scalar(
        select(func.count())
        .select_from(ParserErrorModel)
        .where(ParserErrorModel.occurred_at >= window_start)
    )
    PARSER_ERROR_RATE.set((parser_errors or 0) / RATE_WINDOW_SECONDS)


async def collect_metrics(session: AsyncSession) -> tuple[bytes, str]:
    await refresh_database_metrics(session)
    return generate_latest(), CONTENT_TYPE_LATEST

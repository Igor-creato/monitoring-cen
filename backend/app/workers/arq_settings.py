from urllib.parse import urlparse

from arq import cron, func
from arq.connections import RedisSettings

from app.infra.config import get_settings
from app.workers.context import shutdown, startup
from app.workers.tasks import run_due_monitor_checks, run_monitor_check, send_notification


def redis_settings_from_url(url: str) -> RedisSettings:
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "redis",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


settings = get_settings()


class WorkerSettings:
    functions = [
        func(
            run_monitor_check,
            max_tries=settings.check_max_retries,
            timeout=settings.check_lock_ttl_seconds,
        ),
        func(run_due_monitor_checks, max_tries=1, timeout=30),
        func(send_notification, max_tries=settings.notification_max_retries, timeout=60),
    ]
    redis_settings = redis_settings_from_url(settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = [
        cron(run_due_monitor_checks, minute=None, second=0, max_tries=1),
    ]
    max_jobs = 20
    job_timeout = 120

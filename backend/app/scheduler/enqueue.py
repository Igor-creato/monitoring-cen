from arq import create_pool

from app.workers.arq_settings import redis_settings_from_url


async def enqueue_monitor_check(redis_url: str, monitor_id: int) -> None:
    redis = await create_pool(redis_settings_from_url(redis_url))
    try:
        await redis.enqueue_job("run_monitor_check", monitor_id)
    finally:
        await redis.close()

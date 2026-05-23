from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from redis.asyncio import Redis

_RELEASE_IF_OWNER_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class RedisLock:
    redis: Redis
    key: str
    token: str

    async def release(self) -> None:
        await self.redis.eval(_RELEASE_IF_OWNER_SCRIPT, 1, self.key, self.token)


@asynccontextmanager
async def acquire_redis_lock(
    redis: Redis,
    *,
    key: str,
    ttl_seconds: int,
) -> AsyncIterator[RedisLock | None]:
    token = uuid4().hex
    acquired = await redis.set(key, token, nx=True, ex=ttl_seconds)
    lock = RedisLock(redis=redis, key=key, token=token) if acquired else None
    try:
        yield lock
    finally:
        if lock is not None:
            await lock.release()

import json
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

_redis_pool: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_pool


async def cache_get(key: str) -> Any | None:
    r = get_redis()
    raw = await r.get(key)
    return json.loads(raw) if raw else None


async def cache_set(key: str, value: Any, ttl_seconds: int = 60) -> None:
    r = get_redis()
    await r.set(key, json.dumps(value, default=str), ex=ttl_seconds)


async def cache_invalidate(pattern: str) -> None:
    """Invalidate all keys matching a prefix pattern, e.g. 'jobs:list:*'."""
    r = get_redis()
    async for key in r.scan_iter(match=pattern):
        await r.delete(key)

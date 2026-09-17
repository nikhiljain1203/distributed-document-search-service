from collections.abc import AsyncGenerator

import redis.asyncio as redis

from app.core.config import get_settings

_redis: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    yield await get_redis_client()

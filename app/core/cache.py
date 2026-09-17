import hashlib
import json
import logging
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def search_cache_key(tenant_id: str, q: str, limit: int, offset: int) -> str:
    digest = hashlib.sha256(f"{q}|{limit}|{offset}".encode()).hexdigest()[:24]
    return f"search:{tenant_id}:{digest}"


def doc_cache_key(tenant_id: str, document_id: str) -> str:
    return f"doc:{tenant_id}:{document_id}"


async def cache_get(client: redis.Redis, key: str) -> Any | None:
    try:
        raw = await client.get(key)
    except redis.RedisError:
        logger.warning("Cache get failed for key=%s", key)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Corrupt cache payload for key=%s", key)
        return None


async def cache_set(client: redis.Redis, key: str, value: Any, ttl: int | None = None) -> None:
    ttl = ttl if ttl is not None else get_settings().cache_ttl_seconds
    try:
        await client.set(key, json.dumps(value), ex=ttl)
    except redis.RedisError:
        logger.warning("Cache set failed for key=%s", key)


async def invalidate_tenant_search_cache(client: redis.Redis, tenant_id: str) -> int:
    deleted = 0
    pattern = f"search:{tenant_id}:*"
    try:
        async for key in client.scan_iter(match=pattern, count=100):
            deleted += await client.unlink(key)
    except redis.RedisError:
        logger.warning("Search cache invalidation failed for tenant=%s", tenant_id)
    return deleted


async def invalidate_doc_cache(client: redis.Redis, tenant_id: str, document_id: str) -> None:
    try:
        await client.unlink(doc_cache_key(tenant_id, document_id))
    except redis.RedisError:
        logger.warning("Doc cache invalidation failed for %s/%s", tenant_id, document_id)
